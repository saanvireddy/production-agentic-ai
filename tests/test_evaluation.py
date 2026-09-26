"""Evaluation gates that run on every PR (no LLM needed).
The full Ragas run (LLM-as-judge) lives in app/evaluation/ragas_eval.py and the evaluation workflow."""

import json

import pytest

from app.evaluation.ragas_eval import summarise
from app.evaluation.retrieval import evaluate_retrieval
from app.evaluation.sql_eval import evaluate_sql, result_signature
from app.services.llm import DeterministicFakeLLM
from app.sql.tool import SqlTool

pytestmark = pytest.mark.evaluation


def test_retrieval_quality_gate(vector_store, embeddings):
    report = evaluate_retrieval(vector_store, embeddings, k=4)
    # Baseline measured with the keyword-style HashEmbeddings; nomic-embed-text should beat it.
    assert report.hit_rate_at_k >= 0.9, report.misses
    assert report.mrr >= 0.85, report.misses
    assert report.page_recall_at_k >= 0.85, report.misses


def test_sql_execution_accuracy(tmp_path, sql_executor):
    ds = tmp_path / "sql.json"
    ds.write_text(
        json.dumps(
            [
                {
                    "question": "How many employees are in Engineering?",
                    "gold_sql": "SELECT COUNT(*) FROM employees WHERE department = 'Engineering'",
                },
                {
                    "question": "Compare Engineering and Finance headcount",
                    "gold_sql": "SELECT department, COUNT(*) FROM employees WHERE department IN ('Engineering','Finance') "
                    "GROUP BY department",
                },
            ]
        )
    )
    report = evaluate_sql(SqlTool(DeterministicFakeLLM(), sql_executor), sql_executor, ds)
    # Q1: fake LLM returns (department, count) while gold returns only count -> must be marked wrong.
    assert [r["correct"] for r in report["results"]] == [False, True]


def test_result_signature_ignores_order_and_names():
    a = [{"department": "Finance", "n": 16}, {"department": "Engineering", "n": 48}]
    b = [{"d": "engineering", "count": 48}, {"d": "Finance", "count": 16.0}]
    assert result_signature(a) == result_signature(b)


def test_ragas_summary_math():
    rows = [
        {
            "faithfulness": 1.0,
            "answer_relevancy": 0.8,
            "llm_context_precision_with_reference": 1.0,
            "context_recall": 1.0,
            "_route": "rag",
            "_expected": "a.pdf:p1",
            "_cited": ["a.pdf:p1"],
            "_latency_s": 2.0,
        },
        {
            "faithfulness": 0.5,
            "answer_relevancy": None,
            "llm_context_precision_with_reference": 0.0,
            "context_recall": 0.0,
            "_route": "sql",
            "_expected": "b.pdf:p2",
            "_cited": [],
            "_latency_s": 4.0,
        },
    ]
    s = summarise(rows)
    assert s["faithfulness"] == 0.75
    assert s["answer_relevancy"] == 0.8  # NaN/None rows are excluded, not counted as 0
    assert s["route_accuracy"] == 0.5
    assert s["citation_accuracy"] == 0.5
    assert s["mean_latency_s"] == 3.0
