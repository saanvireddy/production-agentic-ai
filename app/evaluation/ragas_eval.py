"""End-to-end RAG evaluation with Ragas, using a local Ollama model as the judge.

This is a *black-box* evaluation: it talks to the running API over HTTP, exactly like a
user would, so it measures the deployed system (router + retriever + LLM + guardrails).

It runs in its own virtualenv (requirements-eval.txt) because ragas 0.4.x still imports
modules that were removed from langchain-community 0.4, which the app itself uses.

    python -m venv .venv-eval && . .venv-eval/bin/activate
    pip install -r requirements-eval.txt
    python -m app.evaluation.ragas_eval --api http://localhost:8000 \
        --judge-model llama3.1:8b --min-faithfulness 0.7

Metrics:
  faithfulness       - are the answer's claims supported by the retrieved context?
  answer_relevancy   - does the answer address the question?
  context_precision  - are the relevant chunks ranked above irrelevant ones?
  context_recall     - does the retrieved context contain what the reference answer needs?
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import httpx

DATASET = Path(__file__).resolve().parents[2] / "data" / "eval" / "rag_eval.json"


def collect(api: str, username: str, password: str) -> list[dict]:
    items = json.loads(DATASET.read_text())
    with httpx.Client(base_url=api, timeout=300) as c:
        token = c.post("/api/v1/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        rows = []
        for i, it in enumerate(items, 1):
            t0 = time.perf_counter()
            r = c.post("/api/v1/chat", headers=headers, json={"question": it["question"]})
            r.raise_for_status()
            body = r.json()
            contexts = [s["snippet"] for s in body["sources"] if s.get("snippet")] or ["(no context retrieved)"]
            rows.append(
                {
                    "user_input": it["question"],
                    "retrieved_contexts": contexts,
                    "response": body["answer"],
                    "reference": it["ground_truth"],
                    "_route": body["route"],
                    "_cited": [f"{s['source']}:p{s['page']}" for s in body["sources"]],
                    "_expected": f"{it['expected_source']}:p{it['expected_page']}",
                    "_latency_s": round(time.perf_counter() - t0, 2),
                }
            )
            print(f"[{i}/{len(items)}] {body['route']:7} {rows[-1]['_latency_s']:6.1f}s  {it['question']}")
    return rows


def score(rows: list[dict], judge_model: str, embed_model: str, ollama_url: str) -> list[dict]:
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy
    from ragas.run_config import RunConfig

    judge = LangchainLLMWrapper(ChatOllama(model=judge_model, base_url=ollama_url, temperature=0, num_ctx=8192))
    emb = LangchainEmbeddingsWrapper(OllamaEmbeddings(model=embed_model, base_url=ollama_url))
    ds = EvaluationDataset.from_list([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
    result = evaluate(
        ds,
        metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()],
        llm=judge,
        embeddings=emb,
        run_config=RunConfig(timeout=900, max_workers=2, max_retries=3),
        show_progress=True,
    )
    df = result.to_pandas()
    out = []
    for r, (_, s) in zip(rows, df.iterrows(), strict=True):
        out.append(
            {
                **r,
                **{
                    m: (
                        None
                        if s.get(m) is None or (isinstance(s.get(m), float) and math.isnan(s.get(m)))
                        else round(float(s.get(m)), 3)
                    )
                    for m in (
                        "faithfulness",
                        "answer_relevancy",
                        "llm_context_precision_with_reference",
                        "context_recall",
                    )
                },
            }
        )
    return out


def summarise(scored: list[dict]) -> dict:
    def mean(key: str) -> float | None:
        vals = [r[key] for r in scored if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "n": len(scored),
        "faithfulness": mean("faithfulness"),
        "answer_relevancy": mean("answer_relevancy"),
        "context_precision": mean("llm_context_precision_with_reference"),
        "context_recall": mean("context_recall"),
        "route_accuracy": round(sum(r["_route"] == "rag" for r in scored) / len(scored), 3),
        "citation_accuracy": round(sum(r["_expected"] in r["_cited"] for r in scored) / len(scored), 3),
        "mean_latency_s": round(sum(r["_latency_s"] for r in scored) / len(scored), 2),
    }


def write_markdown(summary: dict, scored: list[dict], path: Path, judge: str) -> None:
    lines = [
        "# RAG evaluation results",
        "",
        f"Judge model: `{judge}` (Ollama) - {summary['n']} questions - generated {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Metric | Score |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in summary.items() if k != "n"]
    lines += [
        "",
        "| Question | Faithfulness | Answer relevancy | Context precision | Context recall | Cited |",
        "|---|---|---|---|---|---|",
    ]
    for r in scored:
        lines.append(
            f"| {r['user_input']} | {r.get('faithfulness')} | {r.get('answer_relevancy')} | "
            f"{r.get('llm_context_precision_with_reference')} | {r.get('context_recall')} | "
            f"{', '.join(r['_cited'])} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default=os.getenv("EVAL_API_URL", "http://localhost:8000"))
    p.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
    p.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "admin123"))
    p.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    p.add_argument("--judge-model", default=os.getenv("EVAL_JUDGE_MODEL", "llama3.1:8b"))
    p.add_argument("--embed-model", default=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"))
    p.add_argument("--min-faithfulness", type=float, default=0.0)
    p.add_argument("--min-answer-relevancy", type=float, default=0.0)
    p.add_argument("--out-dir", default="reports")
    a = p.parse_args()

    rows = collect(a.api, a.username, a.password)
    scored = score(rows, a.judge_model, a.embed_model, a.ollama_url)
    summary = summarise(scored)

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ragas_eval.json").write_text(json.dumps({"summary": summary, "rows": scored}, indent=2))
    write_markdown(summary, scored, out / "ragas_eval.md", a.judge_model)
    print(json.dumps(summary, indent=2))

    failed = (summary["faithfulness"] or 0) < a.min_faithfulness or (
        summary["answer_relevancy"] or 0
    ) < a.min_answer_relevancy
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
