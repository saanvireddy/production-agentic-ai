"""SQL guardrails. The LLM never gets to run arbitrary SQL.

Defence in depth, in order:
1. Intent check on the user's question (block "delete all employees" before any LLM call).
2. AST validation with sqlglot:
   - exactly one statement, and it must be a SELECT (UNION/CTE of SELECTs allowed)
   - no DML/DDL nodes anywhere in the tree (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/
     CREATE/GRANT, SELECT ... INTO, COPY, raw commands)
   - only allow-listed tables and columns
   - no dangerous functions (pg_sleep, pg_read_file, dblink, set_config, ...)
3. A LIMIT is injected or clamped to SQL_MAX_ROWS.
4. Execution happens in a READ ONLY transaction with a statement_timeout (see tool.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

READ_ONLY_MESSAGE = "Only read-only SQL operations are supported."

# Tables/columns the SQL tool may touch. users/messages/documents are deliberately excluded.
ALLOWED_SCHEMA: dict[str, dict[str, str]] = {
    "employees": {
        "id": "integer primary key",
        "name": "text",
        "department": "text (references departments.name)",
        "role": "text, job title",
        "salary": "numeric, annual USD",
        "location": "text: Atlanta, Austin, Chicago, Denver or Remote",
        "experience_years": "integer, years of professional experience",
        "hire_date": "date",
    },
    "departments": {
        "id": "integer primary key",
        "name": "text, unique department name",
        "location": "text, department home office",
        "budget": "numeric, annual USD budget",
        "head": "text, department head's name",
    },
}

FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Command,
    exp.Into,
    exp.Merge,
    exp.Grant,
    exp.Copy,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Lock,
)

FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "dblink",
    "dblink_exec",
    "lo_import",
    "lo_export",
    "set_config",
    "current_setting",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "query_to_xml",
    "copy",
}

_WRITE_INTENT = re.compile(
    r"\b(delete|drop|truncate|insert|update|alter|remove|erase|wipe|purge|grant|revoke|"
    r"add (?:a |an )?(?:new )?(?:employee|row|record|column)|"
    r"(?:change|modify|set|raise|increase|decrease|give) (?:the |an? |all |every )?[\w\s']{0,40}?"
    r"(?:salar(?:y|ies)|department|role|budget|record))\b",
    re.I,
)


class SQLGuardrailError(Exception):
    def __init__(self, reason: str, user_message: str = READ_ONLY_MESSAGE):
        super().__init__(reason)
        self.reason = reason
        self.user_message = user_message


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    tables: frozenset[str]


def check_question_intent(question: str) -> None:
    if _WRITE_INTENT.search(question):
        raise SQLGuardrailError("write_intent")


def extract_sql(llm_output: str) -> str:
    """Pull the SQL out of an LLM reply (handles ```sql fences and chatty prefixes)."""
    fenced = re.search(r"```(?:sql)?\s*(.+?)```", llm_output, re.S | re.I)
    text = fenced.group(1) if fenced else llm_output
    m = re.search(r"\b(with|select)\b.*", text, re.S | re.I)
    sql = (m.group(0) if m else text).strip()
    return sql.rstrip(";").strip()


def schema_prompt() -> str:
    lines = []
    for table, cols in ALLOWED_SCHEMA.items():
        lines.append(f"TABLE {table} (")
        lines.extend(f"    {c} -- {desc}" for c, desc in cols.items())
        lines.append(")")
    return "\n".join(lines)


def validate_sql(sql: str, max_rows: int = 100) -> ValidatedSQL:
    if not sql or not sql.strip():
        raise SQLGuardrailError("empty_sql", "I couldn't generate a query for that question.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as exc:
        raise SQLGuardrailError("parse_error", "I couldn't generate a valid query for that question.") from exc

    if len(statements) != 1:
        raise SQLGuardrailError("multiple_statements")
    tree = statements[0]

    if not isinstance(tree, exp.Query):  # Select, Union, Intersect, Except (CTEs hang off these)
        raise SQLGuardrailError(f"not_select:{type(tree).__name__}")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SQLGuardrailError(f"forbidden_node:{type(node).__name__}")
        if isinstance(node, exp.Anonymous | exp.Func):
            fname = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if fname in FORBIDDEN_FUNCTIONS:
                raise SQLGuardrailError(f"forbidden_function:{fname}")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables: set[str] = set()
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if name in cte_names:
            continue
        if t.db and t.db.lower() not in {"public"}:
            raise SQLGuardrailError(f"schema_not_allowed:{t.db}", "That data is not available to the SQL tool.")
        if name not in ALLOWED_SCHEMA:
            raise SQLGuardrailError(f"table_not_allowed:{name}", "That data is not available to the SQL tool.")
        tables.add(name)
    if not tables:
        raise SQLGuardrailError("no_table", "I couldn't generate a query for that question.")

    allowed_cols = {c for tbl in tables for c in ALLOWED_SCHEMA[tbl]}
    aliases = {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    aliases |= {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for col in tree.find_all(exp.Column):
        cname = col.name.lower()
        if cname == "*" or cname in allowed_cols or cname in aliases:
            continue
        raise SQLGuardrailError(f"column_not_allowed:{cname}", "That data is not available to the SQL tool.")

    # Enforce / clamp LIMIT on the outermost query.
    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name) if limit.expression else None
        except (TypeError, ValueError):
            current = None
    if current is None or current > max_rows:
        tree = tree.limit(max_rows, copy=False)

    return ValidatedSQL(sql=tree.sql(dialect="postgres"), tables=frozenset(tables))
