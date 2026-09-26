"""Integration tests against real PostgreSQL/pgvector and Redis (the production wiring,
not the in-memory fakes). The LLM is still the deterministic fake.

    docker compose up -d postgres redis
    pytest -m integration
"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

DB_URL = os.getenv("DATABASE_URL", "postgresql://agentic:agentic@localhost:5432/agentic")


@pytest.fixture(scope="module")
def live_client():
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    with TestClient(create_app(settings=get_settings())) as c:  # runs migrations, seed, ingestion
        yield c


@pytest.fixture(scope="module")
def token(live_client):
    s = __import__("app.config", fromlist=["get_settings"]).get_settings()
    r = live_client.post(
        "/api/v1/auth/login", json={"username": s.admin_username, "password": s.admin_password.get_secret_value()}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_readiness(live_client):
    body = live_client.get("/api/v1/health/ready").json()
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_documents_ingested_into_pgvector(live_client, token):
    docs = {d["filename"]: d for d in live_client.get("/api/v1/documents", headers=token).json()}
    assert {"leave_policy.pdf", "remote_work_policy.pdf"} <= set(docs)
    with psycopg.connect(DB_URL) as conn:
        n = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    assert n >= 15


def test_sql_route_against_postgres(live_client, token):
    body = live_client.post(
        "/api/v1/chat", headers=token, json={"question": "How many employees are in the Engineering department?"}
    ).json()
    assert body["route"] == "sql"
    with psycopg.connect(DB_URL) as conn:
        expected = conn.execute("SELECT COUNT(*) FROM employees WHERE department='Engineering'").fetchone()[0]
    assert body["rows"][0]["headcount"] == expected


def test_rag_route_against_pgvector(live_client, token):
    body = live_client.post(
        "/api/v1/chat", headers=token, json={"question": "How many unused vacation days can be carried over?"}
    ).json()
    assert body["route"] == "rag"
    assert body["sources"][0]["source"] == "leave_policy.pdf"


def test_read_only_transaction_blocks_writes_even_if_validation_is_bypassed():
    """Defence in depth: the executor itself runs in a READ ONLY transaction."""
    from app.sql.tool import PostgresReadOnlyExecutor

    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        PostgresReadOnlyExecutor().execute("DELETE FROM employees")


def test_conversation_memory_in_redis(live_client, token):
    first = live_client.post(
        "/api/v1/chat", headers=token, json={"question": "How many employees are in Sales?"}
    ).json()
    second = live_client.post(
        "/api/v1/chat", headers=token, json={"question": "What about Marketing?", "session_id": first["session_id"]}
    ).json()
    assert second["standalone_question"] == "How many employees are in Marketing?"
