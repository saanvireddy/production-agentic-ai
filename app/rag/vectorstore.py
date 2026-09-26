"""Vector storage: pgvector in PostgreSQL (production) and an in-memory store (tests)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class Chunk:
    content: str
    page: int | None
    chunk_index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    content: str
    source: str
    page: int | None
    score: float
    chunk_index: int = 0

    def citation(self) -> str:
        return f"{self.source}, page {self.page}" if self.page else self.source


@dataclass
class DocumentRecord:
    id: int
    filename: str
    title: str | None
    num_pages: int
    num_chunks: int
    created_at: str | None = None


class VectorStore(Protocol):
    def upsert_document(
        self,
        filename: str,
        title: str | None,
        checksum: str,
        num_pages: int,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        uploaded_by: str | None,
    ) -> int: ...
    def get_checksum(self, filename: str) -> str | None: ...
    def search(self, query_embedding: list[float], k: int) -> list[RetrievedChunk]: ...
    def list_documents(self) -> list[DocumentRecord]: ...
    def delete_document(self, filename: str) -> bool: ...


class PgVectorStore:
    def upsert_document(self, filename, title, checksum, num_pages, chunks, embeddings, uploaded_by=None) -> int:
        from app.database.connection import get_conn

        with get_conn() as conn, conn.transaction():
            # Re-ingesting a file replaces its chunks atomically.
            conn.execute("DELETE FROM documents WHERE filename = %s", (filename,))
            doc_id = conn.execute(
                "INSERT INTO documents (filename, title, checksum, num_pages, num_chunks, uploaded_by) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (filename, title, checksum, num_pages, len(chunks), uploaded_by),
            ).fetchone()["id"]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO document_chunks (document_id, chunk_index, page, content, embedding, metadata) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [
                        (
                            doc_id,
                            c.chunk_index,
                            c.page,
                            c.content,
                            np.array(e, dtype=np.float32),
                            json.dumps(c.metadata),
                        )
                        for c, e in zip(chunks, embeddings, strict=True)
                    ],
                )
        return doc_id

    def get_checksum(self, filename: str) -> str | None:
        from app.database.connection import get_conn

        with get_conn() as conn:
            row = conn.execute("SELECT checksum FROM documents WHERE filename = %s", (filename,)).fetchone()
        return row["checksum"] if row else None

    def search(self, query_embedding: list[float], k: int) -> list[RetrievedChunk]:
        from app.database.connection import get_conn

        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT c.content, c.page, c.chunk_index, d.filename,
                       1 - (c.embedding <=> %(q)s) AS score
                FROM document_chunks c JOIN documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> %(q)s
                LIMIT %(k)s
                """,
                {"q": np.array(query_embedding, dtype=np.float32), "k": k},
            ).fetchall()
        return [
            RetrievedChunk(
                content=r["content"],
                source=r["filename"],
                page=r["page"],
                score=float(r["score"]),
                chunk_index=r["chunk_index"],
            )
            for r in rows
        ]

    def list_documents(self) -> list[DocumentRecord]:
        from app.database.connection import get_conn

        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, filename, title, num_pages, num_chunks, created_at::text AS created_at "
                "FROM documents ORDER BY filename"
            ).fetchall()
        return [DocumentRecord(**r) for r in rows]

    def delete_document(self, filename: str) -> bool:
        from app.database.connection import get_conn

        with get_conn() as conn:
            cur = conn.execute("DELETE FROM documents WHERE filename = %s", (filename,))
            conn.commit()
            return cur.rowcount > 0


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def upsert_document(self, filename, title, checksum, num_pages, chunks, embeddings, uploaded_by=None) -> int:
        doc_id = len(self._docs) + 1 if filename not in self._docs else self._docs[filename]["id"]
        self._docs[filename] = {
            "id": doc_id,
            "title": title,
            "checksum": checksum,
            "num_pages": num_pages,
            "chunks": list(zip(chunks, embeddings, strict=True)),
        }
        return doc_id

    def get_checksum(self, filename: str) -> str | None:
        d = self._docs.get(filename)
        return d["checksum"] if d else None

    def search(self, query_embedding: list[float], k: int) -> list[RetrievedChunk]:
        def cos(a, b):
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)

        scored = [
            RetrievedChunk(
                content=c.content, source=fn, page=c.page, score=cos(query_embedding, e), chunk_index=c.chunk_index
            )
            for fn, d in self._docs.items()
            for c, e in d["chunks"]
        ]
        return sorted(scored, key=lambda r: r.score, reverse=True)[:k]

    def list_documents(self) -> list[DocumentRecord]:
        return [
            DocumentRecord(
                id=d["id"], filename=fn, title=d["title"], num_pages=d["num_pages"], num_chunks=len(d["chunks"])
            )
            for fn, d in sorted(self._docs.items())
        ]

    def delete_document(self, filename: str) -> bool:
        return self._docs.pop(filename, None) is not None
