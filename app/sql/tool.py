"""SQL tool: question -> LLM-generated SQL -> guardrails -> read-only execution -> NL answer."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents import prompts
from app.config import get_settings
from app.monitoring.metrics import GUARDRAIL_BLOCKS, SQL_LATENCY, SQL_QUERIES
from app.monitoring.tracing import tracer
from app.services.llm import invoke_llm
from app.sql.guardrails import (
    SQLGuardrailError,
    check_question_intent,
    extract_sql,
    schema_prompt,
    validate_sql,
)

logger = logging.getLogger(__name__)


class SqlExecutor(Protocol):
    def execute(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]: ...


class PostgresReadOnlyExecutor:
    """Runs a validated query inside a READ ONLY transaction with a statement timeout.
    Even if validation were bypassed, Postgres itself would reject any write."""

    def execute(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        from app.database.connection import get_conn

        s = get_settings()
        with get_conn() as conn, conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(f"SET LOCAL statement_timeout = {int(s.sql_statement_timeout_ms)}")
            cur = conn.execute(sql)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description] if cur.description else []
        return cols, rows


@dataclass
class SqlResult:
    answer: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    executed: bool = False
    blocked_reason: str | None = None


def _jsonable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def conv(v: Any) -> Any:
        if isinstance(v, Decimal):
            return float(v)
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v

    return [{k: conv(v) for k, v in r.items()} for r in rows]


class SqlTool:
    def __init__(self, llm: BaseChatModel, executor: SqlExecutor):
        self.llm = llm
        self.executor = executor

    def run(self, question: str) -> SqlResult:
        s = get_settings()
        try:
            check_question_intent(question)
        except SQLGuardrailError as e:
            GUARDRAIL_BLOCKS.labels("sql", e.reason.split(":")[0]).inc()
            SQL_QUERIES.labels("blocked").inc()
            return SqlResult(answer=e.user_message, blocked_reason=e.reason)

        raw = invoke_llm(self.llm, "sql_generate", prompts.SQL.format(schema=schema_prompt(), question=question))
        candidate = extract_sql(raw)

        try:
            validated = validate_sql(candidate, max_rows=s.sql_max_rows)
        except SQLGuardrailError as e:
            logger.warning("sql blocked (%s): %s", e.reason, candidate)
            GUARDRAIL_BLOCKS.labels("sql", e.reason.split(":")[0]).inc()
            SQL_QUERIES.labels("blocked").inc()
            return SqlResult(answer=e.user_message, sql=candidate, blocked_reason=e.reason)

        with tracer.start_as_current_span("sql.execute") as span:
            span.set_attribute("db.statement", validated.sql)
            t0 = time.perf_counter()
            try:
                cols, rows = self.executor.execute(validated.sql)
            except Exception as exc:  # noqa: BLE001 - surface a safe message, log the detail
                logger.exception("sql execution failed")
                SQL_QUERIES.labels("error").inc()
                return SqlResult(
                    answer="The database query failed, please rephrase the question.",
                    sql=validated.sql,
                    blocked_reason=f"execution_error:{type(exc).__name__}",
                )
            finally:
                SQL_LATENCY.observe(time.perf_counter() - t0)
            span.set_attribute("db.rows", len(rows))

        rows = _jsonable(rows)
        SQL_QUERIES.labels("ok").inc()
        preview = json.dumps(rows[:25], default=str)
        answer = invoke_llm(
            self.llm, "sql_answer", prompts.SQL_ANSWER.format(question=question, sql=validated.sql, rows=preview)
        )
        return SqlResult(answer=answer, sql=validated.sql, columns=cols, rows=rows, executed=True)
