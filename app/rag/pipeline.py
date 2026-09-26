"""RAG tool: embed -> vector search -> relevance filter -> grounded answer with citations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents import prompts
from app.config import get_settings
from app.monitoring.metrics import RAG_REQUESTS, RAG_RETRIEVAL_SCORE
from app.monitoring.tracing import tracer
from app.rag.vectorstore import RetrievedChunk, VectorStore
from app.services.llm import invoke_llm

NO_ANSWER = "I don't know based on the provided documents."


@dataclass
class RagResult:
    answer: str
    sources: list[RetrievedChunk] = field(default_factory=list)  # chunks the answer cites
    retrieved: list[RetrievedChunk] = field(default_factory=list)  # everything that was retrieved
    grounded: bool = False


class RagTool:
    def __init__(self, store: VectorStore, embeddings: Embeddings, llm: BaseChatModel):
        self.store = store
        self.embeddings = embeddings
        self.llm = llm

    def retrieve(self, question: str, k: int | None = None) -> list[RetrievedChunk]:
        s = get_settings()
        with tracer.start_as_current_span("rag.retrieve") as span:
            qvec = self.embeddings.embed_query(question)
            hits = self.store.search(qvec, k or s.retrieval_top_k)
            span.set_attribute("rag.hits", len(hits))
            if hits:
                span.set_attribute("rag.top_score", hits[0].score)
                RAG_RETRIEVAL_SCORE.observe(hits[0].score)
        return hits

    def run(self, question: str) -> RagResult:
        s = get_settings()
        retrieved = self.retrieve(question)
        relevant = [h for h in retrieved if h.score >= s.retrieval_min_score]
        if not relevant:
            RAG_REQUESTS.labels("no_context").inc()
            return RagResult(answer=NO_ANSWER, retrieved=retrieved, grounded=False)

        context = "\n\n".join(f"[{i}] (source: {c.citation()})\n{c.content}" for i, c in enumerate(relevant, 1))
        answer = invoke_llm(self.llm, "rag_answer", prompts.RAG_ANSWER.format(context=context, question=question))

        if NO_ANSWER.lower().rstrip(".") in answer.lower():
            RAG_REQUESTS.labels("unanswerable").inc()
            return RagResult(answer=NO_ANSWER, retrieved=retrieved, grounded=False)

        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 0 < int(n) <= len(relevant)})
        sources = [relevant[i - 1] for i in cited] if cited else relevant[:1]
        RAG_REQUESTS.labels("answered").inc()
        return RagResult(answer=answer, sources=sources, retrieved=retrieved, grounded=True)
