"""LLM factory.

`ollama` -> a real local model through Ollama (default).
`fake`   -> a deterministic stand-in so the whole stack (API, graph, UI, CI) can run
            on machines without Ollama. It is NOT meant to be smart; it only follows
            the prompt markers defined in app.agents.prompts.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.config import Settings, get_settings


class DeterministicFakeLLM(BaseChatModel):
    """Rule-based fake chat model. Recognises which task it is being asked to do
    from the task markers in the prompts and returns a plausible deterministic answer."""

    @property
    def _llm_type(self) -> str:
        return "deterministic-fake"

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        prompt = "\n".join(str(m.content) for m in messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._respond(prompt)))])

    @staticmethod
    def _respond(prompt: str) -> str:
        if "[TASK:ROUTE]" in prompt:
            return "general"
        if "[TASK:REWRITE]" in prompt:
            m = re.search(r"Follow-up question:\s*(.+)", prompt)
            return m.group(1).strip() if m else ""
        if "[TASK:SQL]" in prompt:
            q = prompt.rsplit("Question:", 1)[-1].lower()
            depts = ["Engineering", "Data Science", "Finance", "Sales", "Marketing", "People Operations", "Security"]
            named = [d for d in depts if d.lower() in q]
            if "average salary" in q or "avg salary" in q:
                return (
                    "SELECT department, ROUND(AVG(salary), 2) AS avg_salary FROM employees "
                    "GROUP BY department ORDER BY avg_salary DESC"
                )
            if named:
                in_list = ", ".join(f"'{d}'" for d in named)
                return (
                    f"SELECT department, COUNT(*) AS headcount FROM employees "
                    f"WHERE department IN ({in_list}) GROUP BY department"
                )
            return "SELECT department, COUNT(*) AS headcount FROM employees GROUP BY department"
        if "[TASK:SQL_ANSWER]" in prompt:
            m = re.search(r"Result rows:\s*(.+?)\n\n", prompt, re.S)
            return f"Here is what the employee database returned: {m.group(1).strip() if m else 'no rows'}."
        if "[TASK:RAG_ANSWER]" in prompt:
            # Extractive "answer": the sentence of passage [1] that overlaps most with the question.
            context = prompt.split("Context:", 1)[-1]
            m = re.search(r"^\[1\][^\n]*\n(.+?)(?:\n\[2\]|\n\nQuestion:)", context, re.S | re.M)
            question = prompt.rsplit("Question:", 1)[-1].lower()
            q_words = {w for w in re.findall(r"[a-z0-9]+", question) if len(w) > 3}
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", m.group(1)) if s.strip()] if m else []
            if not sentences:
                return "I don't know based on the provided documents."
            best = max(sentences, key=lambda s: len(q_words & set(re.findall(r"[a-z0-9]+", s.lower()))))
            return f"{best.rstrip('.')}. [1]"
        return "I am running in offline demo mode (LLM_PROVIDER=fake). Start Ollama for real answers."


def invoke_llm(llm: BaseChatModel, task: str, prompt: str) -> str:
    """Single choke point for LLM calls: metrics + a trace span per call."""
    from app.monitoring.metrics import LLM_LATENCY, LLM_REQUESTS
    from app.monitoring.tracing import tracer

    with tracer.start_as_current_span(f"llm.{task}") as span, LLM_LATENCY.labels(task).time():
        span.set_attribute("llm.task", task)
        try:
            out = llm.invoke(prompt)
        except Exception:
            LLM_REQUESTS.labels(task, "error").inc()
            raise
        LLM_REQUESTS.labels(task, "ok").inc()
        text = out.content if isinstance(out.content, str) else str(out.content)
        span.set_attribute("llm.output_chars", len(text))
        return text.strip()


def build_llm(settings: Settings | None = None) -> BaseChatModel:
    s = settings or get_settings()
    if s.llm_provider == "fake":
        return DeterministicFakeLLM()
    from langchain_ollama import ChatOllama

    return ChatOllama(
        base_url=s.ollama_url,
        model=s.llm_model,
        temperature=s.llm_temperature,
        client_kwargs={"timeout": s.llm_timeout_seconds},
    )
