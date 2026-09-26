"""Redis-backed conversation memory, answer cache and rate limiting.

Every operation degrades gracefully: if Redis is down the API keeps answering
(without memory/cache, and the rate limiter fails open) instead of returning 500s.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
from typing import Any

import redis

from app.config import get_settings
from app.monitoring.metrics import CACHE_HITS, CACHE_MISSES, RATE_LIMITED

logger = logging.getLogger(__name__)


def build_redis(url: str | None = None) -> redis.Redis:
    return redis.Redis.from_url(
        url or get_settings().redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
    )


class ConversationMemory:
    """session -> list of {"role", "content"} messages, capped and TTL'd."""

    def __init__(self, client: redis.Redis):
        self.r = client

    @staticmethod
    def _key(username: str, session_id: str) -> str:
        # Namespaced by user so one user can never read another user's session.
        return f"chat:{username}:{session_id}"

    def history(self, username: str, session_id: str) -> list[dict[str, str]]:
        try:
            raw = self.r.lrange(self._key(username, session_id), 0, -1)
            return [json.loads(x) for x in raw]
        except redis.RedisError:
            logger.warning("redis unavailable: memory read skipped")
            return []

    def append(self, username: str, session_id: str, question: str, answer: str) -> None:
        s = get_settings()
        key = self._key(username, session_id)
        try:
            pipe = self.r.pipeline()
            pipe.rpush(
                key,
                json.dumps({"role": "user", "content": question}),
                json.dumps({"role": "assistant", "content": answer}),
            )
            pipe.ltrim(key, -2 * s.memory_max_turns, -1)
            pipe.expire(key, s.memory_ttl_seconds)
            pipe.execute()
        except redis.RedisError:
            logger.warning("redis unavailable: memory write skipped")

    def clear(self, username: str, session_id: str) -> None:
        with contextlib.suppress(redis.RedisError):
            self.r.delete(self._key(username, session_id))


class AnswerCache:
    """Caches final answers keyed on the *standalone* question, so follow-ups that
    resolve to the same question share an entry, while ambiguous ones never collide."""

    def __init__(self, client: redis.Redis, namespace: str = "v1"):
        self.r = client
        self.ns = namespace

    def _key(self, question: str) -> str:
        norm = " ".join(question.lower().split()).rstrip("?.! ")
        return f"cache:{self.ns}:{hashlib.sha256(norm.encode()).hexdigest()}"

    def get(self, question: str) -> dict[str, Any] | None:
        try:
            raw = self.r.get(self._key(question))
        except redis.RedisError:
            return None
        if raw:
            CACHE_HITS.inc()
            return json.loads(raw)
        CACHE_MISSES.inc()
        return None

    def set(self, question: str, payload: dict[str, Any]) -> None:
        with contextlib.suppress(redis.RedisError):
            self.r.set(self._key(question), json.dumps(payload, default=str), ex=get_settings().cache_ttl_seconds)

    def invalidate_all(self) -> int:
        """Called after document ingestion so stale RAG answers aren't served."""
        try:
            keys = list(self.r.scan_iter(f"cache:{self.ns}:*", count=500))
            return self.r.delete(*keys) if keys else 0
        except redis.RedisError:
            return 0


class RateLimiter:
    """Fixed-window limiter: N requests per user per minute."""

    def __init__(self, client: redis.Redis, limit_per_minute: int):
        self.r = client
        self.limit = limit_per_minute

    def check(self, identity: str) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, seconds_until_reset)."""
        window = int(time.time() // 60)
        key = f"ratelimit:{identity}:{window}"
        try:
            pipe = self.r.pipeline()
            pipe.incr(key)
            pipe.expire(key, 61)
            count, _ = pipe.execute()
        except redis.RedisError:
            logger.warning("redis unavailable: rate limiter failing open")
            return True, self.limit, 60
        reset = 60 - int(time.time() % 60)
        if count > self.limit:
            RATE_LIMITED.inc()
            return False, 0, reset
        return True, self.limit - count, reset
