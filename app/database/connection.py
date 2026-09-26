"""PostgreSQL connection pool (psycopg 3) with pgvector type registration."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)


def init_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = ConnectionPool(
            conninfo=s.database_url,
            min_size=s.db_pool_min,
            max_size=s.db_pool_max,
            kwargs={"row_factory": dict_row},
            configure=_configure,
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    with init_pool().connection() as conn:
        yield conn


def apply_schema() -> None:
    """Create the extension and tables. The vector extension must exist before
    register_vector() is called on pooled connections, so use a raw connection."""
    s = get_settings()
    with psycopg.connect(s.database_url, autocommit=True) as conn:
        conn.execute(SCHEMA_PATH.read_text())
    logger.info("database schema applied")


def ping() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - health checks must never raise
        return False
