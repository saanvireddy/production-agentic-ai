"""Hybrid router: a cheap keyword scorer handles the obvious cases in microseconds;
only ambiguous questions pay for an LLM routing call."""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents import prompts
from app.services.llm import invoke_llm

Route = Literal["rag", "sql", "general"]

DEPARTMENTS = ["engineering", "data science", "finance", "sales", "marketing", "people operations", "security"]

_SQL_TERMS = {
    r"\bhow many\b": 2,
    r"\bcount\b": 2,
    r"\bheadcount\b": 3,
    r"\bnumber of (employees|people|staff)\b": 3,
    r"\baverage\b": 2,
    r"\bavg\b": 2,
    r"\bmedian\b": 2,
    r"\bsalar(y|ies)\b": 2,
    r"\bpaid\b": 1,
    r"\btotal\b": 1,
    r"\bbudget\b": 2,
    r"\bcompare\b": 1,
    r"\bhighest\b": 2,
    r"\blowest\b": 2,
    r"\btop \d+\b": 2,
    r"\blist (all )?(the )?employees\b": 3,
    r"\bemployees?\b": 1,
    r"\bstaff\b": 1,
    r"\bdepartments?\b": 1,
    r"\bhired\b": 2,
    r"\bwho (is|are) the\b": 1,
    r"\bmost experienced\b": 2,
    r"\bexperience_years\b": 3,
    r"\bbreakdown\b": 2,
    r"\bper department\b": 3,
}
_RAG_TERMS = {
    r"\bpolic(y|ies)\b": 4,
    r"\bhandbook\b": 4,
    r"\bvacation\b": 2,
    r"\bpto\b": 2,
    r"\bleave\b": 2,
    r"\bremote(ly)?\b": 2,
    r"\bhybrid\b": 2,
    r"\bwork from (home|abroad)\b": 3,
    r"\bbenefits?\b": 2,
    r"\b401\(?k\)?\b": 3,
    r"\binsurance\b": 2,
    r"\bpassword\b": 2,
    r"\bmfa\b": 2,
    r"\bexpenses?\b": 2,
    r"\breimburs\w*\b": 2,
    r"\bstipend\b": 2,
    r"\bsabbatical\b": 3,
    r"\bholidays?\b": 2,
    r"\bparental\b": 2,
    r"\bsick\b": 2,
    r"\btraining\b": 1,
    r"\bprobation\b": 2,
    r"\bintroductory\b": 2,
    r"\beligib\w*\b": 2,
    r"\ballowed\b": 1,
    r"\bcan i\b": 2,
    r"\bam i\b": 1,
    r"\brules?\b": 1,
    r"\bdays?\b": 1,
    r"\bweeks?\b": 1,
    r"\bcarry ?over\b": 2,
    r"\bincident\b": 2,
    r"\bvpn\b": 2,
    r"\bcode of conduct\b": 3,
    r"\bworking hours\b": 3,
    r"\blearning budget\b": 3,
    r"\bwellness\b": 2,
}
_WRITE = re.compile(r"\b(delete|drop|truncate|insert|update|alter|remove all|wipe)\b", re.I)
_GENERAL = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b|"
    r"\bwho are you\b|\bwhat can you do\b|\bhelp me understand what you\b",
    re.I,
)


def _score(q: str, terms: dict[str, int]) -> int:
    return sum(w for pat, w in terms.items() if re.search(pat, q))


def heuristic_route(question: str) -> Route | None:
    q = question.lower()
    if _WRITE.search(q) and re.search(r"\b(employees?|table|records?|departments?|salar)", q):
        return "sql"  # send to the SQL tool so its guardrail can refuse it explicitly
    if _GENERAL.search(q) and len(q.split()) <= 8:
        return "general"
    sql = _score(q, _SQL_TERMS) + 2 * sum(d in q for d in DEPARTMENTS)
    rag = _score(q, _RAG_TERMS)
    # "learning budget" / "security policy" etc. are policy topics, not SQL.
    if rag >= 4 and rag >= sql:
        return "rag"
    if sql - rag >= 2:
        return "sql"
    if rag - sql >= 1 and rag >= 2:
        return "rag"
    return None


def llm_route(llm: BaseChatModel, question: str) -> Route:
    out = invoke_llm(llm, "route", prompts.ROUTER.format(question=question)).lower()
    for r in ("sql", "rag", "general"):
        if re.search(rf"\b{r}\b", out):
            return r  # type: ignore[return-value]
    return "general"


def route_question(llm: BaseChatModel, question: str) -> tuple[Route, str]:
    r = heuristic_route(question)
    if r is not None:
        return r, "heuristic"
    return llm_route(llm, question), "llm"
