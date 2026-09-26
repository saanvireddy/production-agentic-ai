"""Text-to-SQL evaluation by *execution accuracy*: the generated query is correct if it
returns the same values as a hand-written gold query (column names and row order ignored).

    python -m app.evaluation.sql_eval --min-accuracy 0.8
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.sql.tool import SqlExecutor, SqlTool

DATASET = Path(__file__).resolve().parents[2] / "data" / "eval" / "sql_eval.json"


def _norm(v: Any) -> Any:
    if isinstance(v, Decimal | float):
        return round(float(v), 2)
    if isinstance(v, str):
        return v.strip().lower()
    return v


def result_signature(rows: list[dict[str, Any]]) -> Counter:
    """Order- and column-name-insensitive multiset of row values."""
    return Counter(tuple(sorted((_norm(v) for v in r.values()), key=repr)) for r in rows)


def evaluate_sql(tool: SqlTool, executor: SqlExecutor, dataset: Path = DATASET) -> dict[str, Any]:
    items = json.loads(dataset.read_text())
    results = []
    for it in items:
        _, gold_rows = executor.execute(it["gold_sql"])
        res = tool.run(it["question"])
        ok = res.executed and result_signature(res.rows) == result_signature(gold_rows)
        results.append(
            {"question": it["question"], "correct": ok, "generated_sql": res.sql, "blocked_reason": res.blocked_reason}
        )
    acc = sum(r["correct"] for r in results) / len(results)
    return {"n": len(results), "execution_accuracy": round(acc, 3), "results": results}


def main() -> None:
    from app.config import get_settings
    from app.services.llm import build_llm
    from app.sql.tool import PostgresReadOnlyExecutor

    p = argparse.ArgumentParser()
    p.add_argument("--min-accuracy", type=float, default=0.0)
    p.add_argument("--out", default="reports/sql_eval.json")
    a = p.parse_args()

    executor = PostgresReadOnlyExecutor()
    report = evaluate_sql(SqlTool(build_llm(get_settings()), executor), executor)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2))
    for r in report["results"]:
        print(f"{'PASS' if r['correct'] else 'FAIL'}  {r['question']}\n      {r['generated_sql']}")
    print(f"\nexecution accuracy: {report['execution_accuracy']:.1%} ({report['n']} questions)")
    sys.exit(1 if report["execution_accuracy"] < a.min_accuracy else 0)


if __name__ == "__main__":
    main()
