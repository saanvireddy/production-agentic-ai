"""Embedding providers.

* OllamaNomicEmbeddings: nomic-embed-text via Ollama, with the task prefixes the
  model was trained with ("search_query: " / "search_document: ").
* HashEmbeddings: dependency-free hashed bag-of-words (+ bigrams). Deterministic,
  needs no model download, and good enough for keyword-style retrieval, which makes
  it ideal for unit tests and the CI retrieval-regression gate.
"""

from __future__ import annotations

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

from app.config import Settings, get_settings

_STOP = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its me my of on or our "
    "the their them there these this to was what when where which who why will with you your "
    "about after any all per than that up".split()
)


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    out = []
    for w in words:
        if w in _STOP:
            continue
        # light stemming so "policies"/"policy", "days"/"day" collide
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


class HashEmbeddings(Embeddings):
    def __init__(self, dim: int = 768):
        self.dim = dim

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = int(hashlib.md5(feature.encode(), usedforsecurity=False).hexdigest(), 16)
        return h % self.dim, 1.0 if (h >> 64) & 1 else -1.0

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = _tokens(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        for f in feats:
            idx, sign = self._bucket(f)
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OllamaNomicEmbeddings(Embeddings):
    def __init__(self, base_url: str, model: str):
        from langchain_ollama import OllamaEmbeddings

        self._inner = OllamaEmbeddings(base_url=base_url, model=model)
        self._prefix = "nomic" in model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._prefix:
            texts = [f"search_document: {t}" for t in texts]
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._inner.embed_query(f"search_query: {text}" if self._prefix else text)


def build_embeddings(settings: Settings | None = None) -> Embeddings:
    s = settings or get_settings()
    if s.embedding_provider == "hash":
        return HashEmbeddings(s.embedding_dim)
    return OllamaNomicEmbeddings(s.ollama_url, s.embedding_model)
