"""Test fixtures. Everything runs in-process: no Postgres, Redis or Ollama required.

* LLM        -> DeterministicFakeLLM (LLM_PROVIDER=fake)
* Embeddings -> HashEmbeddings
* Vectors    -> InMemoryVectorStore, loaded with the real sample PDFs
* SQL        -> SQLite in memory, loaded with the same seeded employee data as Postgres
* Redis      -> fakeredis
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

os.environ.update(
    {
        "ENVIRONMENT": "ci",
        "LLM_PROVIDER": "fake",
        "EMBEDDING_PROVIDER": "hash",
        "JWT_SECRET": "test-secret-key-that-is-long-enough-for-hs256",
        "RATE_LIMIT_PER_MINUTE": "1000",
        "OTEL_ENABLED": "false",
        "RETRIEVAL_MIN_SCORE": "0.1",  # hash embeddings produce lower cosine scores than nomic
    }
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.users import InMemoryUserRepository  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database.seed import DEPARTMENTS, generate_employees  # noqa: E402
from app.rag.embeddings import HashEmbeddings  # noqa: E402
from app.rag.ingestion import ingest_directory  # noqa: E402
from app.rag.vectorstore import InMemoryVectorStore  # noqa: E402
from app.services.container import Container, NullChatAudit  # noqa: E402
from app.services.llm import DeterministicFakeLLM  # noqa: E402
from app.services.redis_store import AnswerCache, ConversationMemory, RateLimiter  # noqa: E402

get_settings.cache_clear()
ROOT = Path(__file__).resolve().parents[1]


class SqliteExecutor:
    """Executes validated SELECTs against SQLite seeded with the production seed data."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT, location TEXT, budget REAL, head TEXT);"
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, department TEXT, role TEXT, salary REAL,"
            " location TEXT, experience_years INT, hire_date TEXT);"
        )
        self.conn.executemany(
            "INSERT INTO departments (name, location, budget, head) VALUES (?,?,?,?)", [d[:4] for d in DEPARTMENTS]
        )
        self.conn.executemany(
            "INSERT INTO employees (name, department, role, salary, location, experience_years, hire_date) "
            "VALUES (?,?,?,?,?,?,?)",
            [(*r[:6], r[6].isoformat()) for r in generate_employees()],
        )
        self.executed: list[str] = []

    def execute(self, sql: str):
        self.executed.append(sql)
        cur = self.conn.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, rows


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def embeddings():
    return HashEmbeddings(768)


@pytest.fixture(scope="session")
def vector_store(embeddings):
    store = InMemoryVectorStore()
    ingest_directory(ROOT / "data" / "documents", store, embeddings)
    return store


@pytest.fixture
def sql_executor():
    return SqliteExecutor()


@pytest.fixture
def container(settings, embeddings, vector_store, sql_executor):
    r = fakeredis.FakeRedis(decode_responses=True)
    return Container(
        settings=settings,
        llm=DeterministicFakeLLM(),
        embeddings=embeddings,
        store=vector_store,
        sql_executor=sql_executor,
        users=InMemoryUserRepository({"admin": ("admin-pass", "admin"), "alice": ("alice-pass", "user")}),
        memory=ConversationMemory(r),
        cache=AnswerCache(r),
        rate_limiter=RateLimiter(r, settings.rate_limit_per_minute),
        audit=NullChatAudit(),
    )


@pytest.fixture
def client(container):
    from app.main import create_app

    with TestClient(create_app(container=container)) as c:
        yield c


def _token(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def user_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'alice', 'alice-pass')}"}


@pytest.fixture
def admin_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'admin', 'admin-pass')}"}
