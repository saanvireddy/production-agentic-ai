"""One-shot environment bootstrap: schema -> seed -> document ingestion.

Runs at API startup locally, and as a Kubernetes Job / Helm pre-install hook in the cluster
(where API pods set AUTO_MIGRATE/AUTO_SEED/AUTO_INGEST=false). A Postgres advisory lock
makes it safe even if several replicas start at the same time.

    python -m app.database.bootstrap
"""

from __future__ import annotations

import logging

import psycopg
from langchain_core.embeddings import Embeddings

from app.config import get_settings
from app.rag.vectorstore import VectorStore

logger = logging.getLogger(__name__)
BOOTSTRAP_LOCK_ID = 7_310_422


def bootstrap(
    store: VectorStore, embeddings: Embeddings, migrate: bool = True, seed: bool = True, ingest: bool = True
) -> None:
    from app.database.connection import apply_schema
    from app.database.seed import seed_admin_user, seed_hr_data
    from app.rag.ingestion import ingest_directory

    s = get_settings()
    if not (migrate or seed or ingest):
        return
    with psycopg.connect(s.database_url, autocommit=True) as lock_conn:
        lock_conn.execute("SELECT pg_advisory_lock(%s)", (BOOTSTRAP_LOCK_ID,))
        try:
            if migrate:
                apply_schema()
            if seed:
                seed_admin_user()
                seed_hr_data()
            if ingest:
                try:
                    results = ingest_directory(s.documents_dir, store, embeddings)
                    logger.info("ingestion", extra={"documents": [f"{r.filename}:{r.status}" for r in results]})
                except Exception:  # noqa: BLE001 - e.g. embedding model not pulled yet; the API should still start
                    logger.exception("ingestion failed; re-run `python -m scripts.ingest` once the model is available")
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (BOOTSTRAP_LOCK_ID,))


def main() -> None:
    from app.monitoring.logging import setup_logging
    from app.rag.embeddings import build_embeddings
    from app.rag.vectorstore import PgVectorStore

    setup_logging()
    s = get_settings()
    bootstrap(PgVectorStore(), build_embeddings(s))
    logger.info("bootstrap complete")


if __name__ == "__main__":
    main()
