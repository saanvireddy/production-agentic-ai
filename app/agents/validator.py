"""Response guardrails applied to every answer before it leaves the graph."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.rag.pipeline import NO_ANSWER

MAX_ANSWER_CHARS = 4000
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


@dataclass
class Validation:
    passed: bool = True
    checks: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text)}


def _normalise_num(n: str) -> str:
    try:
        f = float(n)
        return str(int(f)) if f.is_integer() else str(round(f, 2))
    except ValueError:
        return n


def unsupported_numbers(answer: str, evidence: str) -> set[str]:
    """Numbers stated in the answer that never appear in the evidence -> likely hallucinated.
    Citation markers like [1] and small list ordinals are ignored."""
    stripped = re.sub(r"\[\d+\]", "", answer)
    evid = {_normalise_num(n) for n in _numbers(evidence)}
    missing = set()
    for n in _numbers(stripped):
        norm = _normalise_num(n)
        if norm in evid or (norm.isdigit() and int(norm) <= 1):
            continue
        missing.add(n)
    return missing


def validate_response(
    route: str,
    answer: str,
    *,
    sources: list | None = None,
    rows: list | None = None,
    executed: bool = False,
    blocked: bool = False,
    evidence_text: str = "",
) -> tuple[str, Validation]:
    v = Validation()
    answer = (answer or "").strip()

    v.checks["non_empty"] = bool(answer)
    if not answer:
        answer = "Sorry, I couldn't produce an answer. Please try rephrasing."
        v.passed = False

    if len(answer) > MAX_ANSWER_CHARS:
        answer = answer[:MAX_ANSWER_CHARS].rsplit(" ", 1)[0] + " ..."
        v.warnings.append("answer_truncated")

    if route == "rag":
        grounded = bool(sources) or answer == NO_ANSWER
        v.checks["has_supporting_context"] = grounded
        if not grounded:
            v.passed = False
            answer = NO_ANSWER
        elif sources:
            bad = unsupported_numbers(answer, evidence_text)
            v.checks["numbers_supported_by_sources"] = not bad
            if bad:
                v.warnings.append(f"unsupported_numbers:{sorted(bad)}")
                answer += "\n\nNote: some figures in this answer could not be verified against the cited sources."

    elif route == "sql":
        v.checks["sql_executed"] = executed
        if not executed:
            v.passed = blocked  # a deliberate guardrail block is a correct outcome
        else:
            bad = unsupported_numbers(answer, json.dumps(rows or [], default=str))
            v.checks["numbers_supported_by_rows"] = not bad
            if bad:
                v.warnings.append(f"unsupported_numbers:{sorted(bad)}")

    return answer, v
