"""The LangGraph agent.

    START -> contextualize -> router -> {rag | sql | general} -> validator -> END

* contextualize: turns follow-ups ("What about Finance?") into standalone questions
  using the conversation history loaded from Redis.
* router: hybrid heuristic/LLM tool selection.
* rag / sql / general: the three tools.
* validator: response guardrails (grounding, numeric hallucination check, format).
"""

from __future__ import annotations

import re
import time
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agents import prompts
from app.agents.router import DEPARTMENTS, route_question
from app.agents.validator import validate_response
from app.monitoring.metrics import AGENT_LATENCY, AGENT_ROUTE
from app.monitoring.tracing import tracer
from app.rag.pipeline import RagTool
from app.services.llm import invoke_llm
from app.sql.tool import SqlTool


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    standalone_question: str
    route: str
    route_method: str
    answer: str
    sources: list[dict[str, Any]]
    sql: str | None
    rows: list[dict[str, Any]]
    executed: bool
    blocked_reason: str | None
    evidence_text: str
    validation: dict[str, Any]
    latency_ms: dict[str, float]


_FOLLOW_UP = re.compile(
    r"^\s*(what about|how about|and( for)?|same for|what of|now|ok(ay)?,? (what|how) about)\b", re.I
)
_PRONOUN = re.compile(r"\b(it|they|them|that|those|these|there|their|this one)\b", re.I)


def _dept_substitution(question: str, history: list[dict[str, str]]) -> str | None:
    """Deterministic fast path for the most common follow-up shape:
    previous question mentions department A, follow-up is 'what about B?'."""
    if not _FOLLOW_UP.search(question):
        return None
    q_lower = question.lower()
    new = [d for d in DEPARTMENTS if d in q_lower]
    if not new:
        return None
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    if not last_user:
        return None
    old = [d for d in DEPARTMENTS if d in last_user.lower()]
    if len(old) != 1:
        return None
    return re.sub(re.escape(old[0]), new[0].title(), last_user, flags=re.I)


def _needs_rewrite(question: str) -> bool:
    return bool(_FOLLOW_UP.search(question) or _PRONOUN.search(question) or len(question.split()) <= 4)


def _fmt_history(history: list[dict[str, str]], max_turns: int = 6) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in history[-max_turns * 2 :]) or "(none)"


def build_agent(llm: BaseChatModel, rag_tool: RagTool, sql_tool: SqlTool):
    def timed(name: str, state: AgentState, t0: float) -> dict[str, float]:
        lat = dict(state.get("latency_ms") or {})
        lat[name] = round((time.perf_counter() - t0) * 1000, 1)
        return lat

    def contextualize(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        q, history = state["question"], state.get("history") or []
        standalone = q
        if history and _needs_rewrite(q):
            with tracer.start_as_current_span("agent.contextualize"):
                standalone = (
                    _dept_substitution(q, history)
                    or invoke_llm(llm, "rewrite", prompts.REWRITE.format(history=_fmt_history(history), question=q))
                    or q
                )
        return {"standalone_question": standalone.strip(), "latency_ms": timed("contextualize", state, t0)}

    def router(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        with tracer.start_as_current_span("agent.router") as span:
            route, method = route_question(llm, state["standalone_question"])
            span.set_attribute("agent.route", route)
            span.set_attribute("agent.route_method", method)
        AGENT_ROUTE.labels(route, method).inc()
        return {"route": route, "route_method": method, "latency_ms": timed("router", state, t0)}

    def rag(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        with tracer.start_as_current_span("tool.rag"):
            res = rag_tool.run(state["standalone_question"])
        return {
            "answer": res.answer,
            "sources": [
                {"source": c.source, "page": c.page, "score": round(c.score, 4), "snippet": c.content}
                for c in res.sources
            ],
            "evidence_text": "\n".join(c.content for c in res.sources),
            "latency_ms": timed("rag", state, t0),
        }

    def sql(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        with tracer.start_as_current_span("tool.sql"):
            res = sql_tool.run(state["standalone_question"])
        return {
            "answer": res.answer,
            "sql": res.sql,
            "rows": res.rows[:50],
            "executed": res.executed,
            "blocked_reason": res.blocked_reason,
            "sources": [{"source": "employee database", "page": None, "score": None, "snippet": res.sql}]
            if res.executed
            else [],
            "latency_ms": timed("sql", state, t0),
        }

    def general(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        with tracer.start_as_current_span("tool.general"):
            answer = invoke_llm(
                llm,
                "general",
                prompts.GENERAL.format(history=_fmt_history(state.get("history") or []), question=state["question"]),
            )
        return {"answer": answer, "sources": [], "latency_ms": timed("general", state, t0)}

    def validator(state: AgentState) -> AgentState:
        t0 = time.perf_counter()
        answer, v = validate_response(
            state["route"],
            state.get("answer", ""),
            sources=state.get("sources"),
            rows=state.get("rows"),
            executed=state.get("executed", False),
            blocked=bool(state.get("blocked_reason")),
            evidence_text=state.get("evidence_text", ""),
        )
        return {
            "answer": answer,
            "validation": {"passed": v.passed, "checks": v.checks, "warnings": v.warnings},
            "latency_ms": timed("validator", state, t0),
        }

    g = StateGraph(AgentState)
    g.add_node("contextualize", contextualize)
    g.add_node("router", router)
    g.add_node("rag", rag)
    g.add_node("sql", sql)
    g.add_node("general", general)
    g.add_node("validator", validator)
    g.add_edge(START, "contextualize")
    g.add_edge("contextualize", "router")
    g.add_conditional_edges("router", lambda s: s["route"], {"rag": "rag", "sql": "sql", "general": "general"})
    for n in ("rag", "sql", "general"):
        g.add_edge(n, "validator")
    g.add_edge("validator", END)
    return g.compile()


def run_agent(agent, question: str, history: list[dict[str, str]] | None = None) -> AgentState:
    t0 = time.perf_counter()
    with tracer.start_as_current_span("agent.run") as span:
        result: AgentState = agent.invoke({"question": question, "history": history or [], "latency_ms": {}})
        span.set_attribute("agent.route", result.get("route", ""))
    total = time.perf_counter() - t0
    AGENT_LATENCY.labels(result.get("route", "unknown")).observe(total)
    result.setdefault("latency_ms", {})["total"] = round(total * 1000, 1)
    return result
