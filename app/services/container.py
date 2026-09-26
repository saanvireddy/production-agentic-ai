"""Dependency container. Production wiring lives in `build_container`; tests build a
Container from in-memory fakes, so no test needs Postgres, Redis or Ollama."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.graph import build_agent
from app.auth.users import UserRepository
from app.config import Settings
from app.rag.pipeline import RagTool
from app.rag.vectorstore import VectorStore
from app.services.redis_store import AnswerCache, ConversationMemory, RateLimiter
from app.sql.tool import SqlExecutor, SqlTool

logger = logging.getLogger(__name__)


class ChatAudit(Protocol):
    def log(self, session_id: str, username: str, question: str, answer: str, route: str, latency_ms: int) -> None: ...


class PostgresChatAudit:
    def log(self, session_id, username, question, answer, route, latency_ms) -> None:
        from app.database.connection import get_conn

        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return
        try:
            with get_conn() as conn, conn.transaction():
                conn.execute(
                    "INSERT INTO chat_sessions (id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (sid, username)
                )
                conn.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (%s, 'user', %s)", (sid, question)
                )
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, route, latency_ms) "
                    "VALUES (%s, 'assistant', %s, %s, %s)",
                    (sid, answer, route, latency_ms),
                )
        except Exception:  # noqa: BLE001 - auditing must never break a response
            logger.exception("failed to write chat audit")


class NullChatAudit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def log(self, session_id, username, question, answer, route, latency_ms) -> None:
        self.entries.append({"session_id": session_id, "username": username, "route": route})


@dataclass
class Container:
    settings: Settings
    llm: BaseChatModel
    embeddings: Embeddings
    store: VectorStore
    sql_executor: SqlExecutor
    users: UserRepository
    memory: ConversationMemory
    cache: AnswerCache
    rate_limiter: RateLimiter
    audit: ChatAudit
    db_ping: Callable[[], bool] = lambda: True
    agent: Any = field(init=False)

    def __post_init__(self) -> None:
        self.rag_tool = RagTool(self.store, self.embeddings, self.llm)
        self.sql_tool = SqlTool(self.llm, self.sql_executor)
        self.agent = build_agent(self.llm, self.rag_tool, self.sql_tool)


def build_container(settings: Settings) -> Container:
    from app.auth.users import PostgresUserRepository
    from app.database.connection import ping
    from app.rag.embeddings import build_embeddings
    from app.rag.vectorstore import PgVectorStore
    from app.services.llm import build_llm
    from app.services.redis_store import build_redis
    from app.sql.tool import PostgresReadOnlyExecutor

    r = build_redis(settings.redis_url)
    return Container(
        settings=settings,
        llm=build_llm(settings),
        embeddings=build_embeddings(settings),
        store=PgVectorStore(),
        sql_executor=PostgresReadOnlyExecutor(),
        users=PostgresUserRepository(),
        memory=ConversationMemory(r),
        cache=AnswerCache(r, namespace=f"{settings.llm_model}:{settings.embedding_model}"),
        rate_limiter=RateLimiter(r, settings.rate_limit_per_minute),
        audit=PostgresChatAudit(),
        db_ping=ping,
    )
