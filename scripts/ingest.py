"""Ingest every document in DOCUMENTS_DIR into pgvector.

python -m scripts.ingest            # skip unchanged files (checksum)
python -m scripts.ingest --force    # re-embed everything (e.g. after changing the embedding model)
"""

from __future__ import annotations

import argparse
import logging

from app.config import get_settings
from app.database.connection import apply_schema
from app.rag.embeddings import build_embeddings
from app.rag.ingestion import ingest_directory
from app.rag.vectorstore import PgVectorStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dir", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    apply_schema()
    for r in ingest_directory(args.dir or s.documents_dir, PgVectorStore(), build_embeddings(s), force=args.force):
        print(f"{r.filename:32} {r.status:10} pages={r.num_pages} chunks={r.num_chunks}")


if __name__ == "__main__":
    main()
