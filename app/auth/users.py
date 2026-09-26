"""User storage behind a small interface so tests can swap Postgres for memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.auth.security import hash_password, verify_password


@dataclass
class User:
    username: str
    role: str
    hashed_password: str = ""
    is_active: bool = True


class UserRepository(Protocol):
    def get(self, username: str) -> User | None: ...


class PostgresUserRepository:
    def get(self, username: str) -> User | None:
        from app.database.connection import get_conn

        with get_conn() as conn:
            row = conn.execute(
                "SELECT username, role, hashed_password, is_active FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        return User(**row) if row else None


class InMemoryUserRepository:
    def __init__(self, users: dict[str, tuple[str, str]] | None = None):
        # username -> (password, role)
        self._users = {
            name: User(username=name, role=role, hashed_password=hash_password(pw))
            for name, (pw, role) in (users or {}).items()
        }

    def get(self, username: str) -> User | None:
        return self._users.get(username)


def authenticate(repo: UserRepository, username: str, password: str) -> User | None:
    user = repo.get(username)
    if user is None or not user.is_active:
        # Still run a hash comparison so response time doesn't reveal valid usernames.
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.hashed_password) else None


_DUMMY_HASH = hash_password("timing-attack-dummy")
