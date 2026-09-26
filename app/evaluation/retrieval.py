"""Retrieval evaluation: does the right document/page come back for each question?

Needs no LLM, so it runs in seconds on every pull request and acts as the regression
gate for chunking, embedding and vector-search changes.

    python -m app.evaluation.retrieval                          # against pgvector (configured embeddings)
    python -m app.evaluation.retrieval --min-hit-rate 0.85 --min-mrr 0.75
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from langchain_core.embeddings import Embeddings

from app.rag.vectorstore import VectorStore

DATASET = Path(__file__).resolve().parents[2] / "data" / "eval" / "rag_eval.json"


@dataclass
class RetrievalReport:
    n: int
    hit_rate_at_1: float  # expected document ranked first
    hit_rate_at_k: float  # expected document anywhere in top-k
    page_recall_at_k: float  # expected document AND page in top-k
    mrr: float  # mean reciprocal rank of the expected document
    k: int
    misses: list[dict]


def evaluate_retrieval(
    store: VectorStore, embeddings: Embeddings, k: int = 4, dataset: Path = DATASET
) -> RetrievalReport:
    items = json.loads(dataset.read_text())
    h1 = hk = pk = 0
    rr = 0.0
    misses = []
    for it in items:
        hits = store.search(embeddings.embed_query(it["question"]), k)
        sources = [h.source for h in hits]
        rank = next((i for i, s in enumerate(sources, 1) if s == it["expected_source"]), None)
        h1 += rank == 1
        hk += rank is not None
        pk += any(h.source == it["expected_source"] and h.page == it.get("expected_page") for h in hits)
        rr += 1 / rank if rank else 0
        if rank != 1:
            misses.append(
                {
                    "question": it["question"],
                    "expected": it["expected_source"],
                    "got": [f"{h.source}:p{h.page}:{h.score:.2f}" for h in hits],
                }
            )
    n = len(items)
    return RetrievalReport(
        n=n,
        hit_rate_at_1=round(h1 / n, 3),
        hit_rate_at_k=round(hk / n, 3),
        page_recall_at_k=round(pk / n, 3),
        mrr=round(rr / n, 3),
        k=k,
        misses=misses,
    )


def main() -> None:
    from app.config import get_settings
    from app.rag.embeddings import build_embeddings
    from app.rag.vectorstore import PgVectorStore

    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--min-hit-rate", type=float, default=0.0, help="fail if hit_rate@k is below this")
    p.add_argument("--min-mrr", type=float, default=0.0, help="fail if MRR is below this")
    p.add_argument("--out", default="reports/retrieval_eval.json")
    a = p.parse_args()

    report = evaluate_retrieval(PgVectorStore(), build_embeddings(get_settings()), k=a.k)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(asdict(report), indent=2))
    print(json.dumps({k: v for k, v in asdict(report).items() if k != "misses"}, indent=2))
    for m in report.misses:
        print(f"  not ranked #1: {m['question']!r} expected={m['expected']} got={m['got']}")

    failed = report.hit_rate_at_k < a.min_hit_rate or report.mrr < a.min_mrr
    if failed:
        print(f"FAIL: thresholds hit_rate@k>={a.min_hit_rate}, mrr>={a.min_mrr}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
