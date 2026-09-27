"""Document ingestion: PDF/Markdown/Text -> clean -> chunk -> embed -> pgvector.

Chunking is done per page so every chunk keeps an exact page number for citations.
Each chunk is embedded together with a short header (the document title), which
measurably helps retrieval when a chunk's own text doesn't name its topic.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.config import get_settings
from app.monitoring.metrics import DOCUMENTS_INGESTED
from app.rag.vectorstore import Chunk, VectorStore

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass
class IngestResult:
    filename: str
    status: str  # "ingested" | "unchanged"
    num_pages: int
    num_chunks: int


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(filename: str, data: bytes) -> tuple[str | None, list[str]]:
    """Return (title, [page_text, ...])."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        title = (reader.metadata.title if reader.metadata else None) or None
        return title, [clean_text(p.extract_text() or "") for p in reader.pages]
    if suffix in {".md", ".txt"}:
        text = clean_text(data.decode("utf-8", errors="replace"))
        first = text.splitlines()[0].lstrip("# ").strip() if text else None
        return first, [text]
    raise ValueError(f"unsupported file type: {suffix}")


def chunk_pages(pages: list[str], title: str | None) -> list[Chunk]:
    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap, separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks: list[Chunk] = []
    for page_no, page_text in enumerate(pages, start=1):
        if not page_text:
            continue
        for piece in splitter.split_text(page_text):
            chunks.append(Chunk(content=piece, page=page_no, chunk_index=len(chunks), metadata={"title": title}))
    return chunks


def ingest_bytes(
    filename: str,
    data: bytes,
    store: VectorStore,
    embeddings: Embeddings,
    uploaded_by: str | None = None,
    force: bool = False,
) -> IngestResult:
    filename = Path(filename).name  # strip any client-supplied path
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type; allowed: {sorted(SUPPORTED_EXTENSIONS)}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("file too large (max 10 MB)")

    # The checksum covers the file AND the embedding model, so switching models (e.g. from the
    # offline hash embeddings to nomic-embed-text) automatically re-embeds instead of silently
    # mixing vectors from two different embedding spaces.
    s = get_settings()
    checksum = f"{hashlib.sha256(data).hexdigest()}:{s.embedding_provider}:{s.embedding_model}"
    if not force and store.get_checksum(filename) == checksum:
        existing = next((d for d in store.list_documents() if d.filename == filename), None)
        return IngestResult(
            filename, "unchanged", existing.num_pages if existing else 0, existing.num_chunks if existing else 0
        )

    title, pages = extract_pages(filename, data)
    chunks = chunk_pages(pages, title)
    if not chunks:
        raise ValueError("no extractable text found (scanned PDFs need OCR first)")

    header = f"{title}\n" if title else ""
    vectors = embeddings.embed_documents([header + c.content for c in chunks])
    store.upsert_document(filename, title, checksum, len(pages), chunks, vectors, uploaded_by)
    DOCUMENTS_INGESTED.inc()
    logger.info("ingested %s: %s pages, %s chunks", filename, len(pages), len(chunks))
    return IngestResult(filename, "ingested", len(pages), len(chunks))


def ingest_directory(
    directory: str | Path, store: VectorStore, embeddings: Embeddings, force: bool = False
) -> list[IngestResult]:
    results = []
    for path in sorted(Path(directory).iterdir()):
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(ingest_bytes(path.name, path.read_bytes(), store, embeddings, "system", force))
    return results
