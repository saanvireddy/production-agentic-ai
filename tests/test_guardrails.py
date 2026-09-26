import pytest

from app.agents.validator import unsupported_numbers, validate_response
from app.rag.pipeline import NO_ANSWER
from app.sql.guardrails import SQLGuardrailError, check_question_intent, extract_sql, validate_sql

# ---------------- SQL: allowed ----------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM employees WHERE department = 'Engineering'",
        "SELECT department, COUNT(*) AS headcount FROM employees GROUP BY department",
        "SELECT e.name, d.head FROM employees e JOIN departments d ON d.name = e.department",
        "WITH x AS (SELECT department, AVG(salary) AS avg_salary FROM employees GROUP BY department) "
        "SELECT * FROM x ORDER BY avg_salary DESC",
        "SELECT name FROM employees UNION SELECT head FROM departments",
    ],
)
def test_select_allowed(sql):
    v = validate_sql(sql)
    assert v.sql.upper().startswith(("SELECT", "WITH"))


# ---------------- SQL: blocked ----------------


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("DELETE FROM employees", "not_select"),
        ("DROP TABLE employees", "not_select"),
        ("UPDATE employees SET salary = 0", "not_select"),
        ("INSERT INTO employees (name) VALUES ('x')", "not_select"),
        ("ALTER TABLE employees ADD COLUMN x int", "not_select"),
        ("TRUNCATE employees", "not_select"),
        ("SELECT 1 FROM employees; DROP TABLE employees", "multiple_statements"),
        ("SELECT * INTO backup FROM employees", "forbidden_node"),
        ("SELECT * FROM users", "table_not_allowed"),
        ("SELECT * FROM pg_catalog.pg_user", "schema_not_allowed"),
        ("SELECT * FROM information_schema.tables", "schema_not_allowed"),
        ("SELECT pg_sleep(10) FROM employees", "forbidden_function"),
        ("SELECT password FROM employees", "column_not_allowed"),
        ("WITH d AS (DELETE FROM employees RETURNING *) SELECT * FROM d", "forbidden_node"),
        ("", "empty_sql"),
    ],
)
def test_dangerous_sql_blocked(sql, reason):
    with pytest.raises(SQLGuardrailError) as exc:
        validate_sql(sql)
    assert exc.value.reason.startswith(reason)


def test_limit_injected_and_clamped():
    assert "LIMIT 100" in validate_sql("SELECT name FROM employees", max_rows=100).sql
    assert "LIMIT 100" in validate_sql("SELECT name FROM employees LIMIT 100000", max_rows=100).sql
    assert "LIMIT 5" in validate_sql("SELECT name FROM employees LIMIT 5", max_rows=100).sql


@pytest.mark.parametrize(
    "q",
    [
        "Delete all employees",
        "drop the employees table",
        "Give everyone in Sales a salary raise",
        "update the Finance budget",
        "add a new employee named Bob",
    ],
)
def test_write_intent_blocked(q):
    with pytest.raises(SQLGuardrailError):
        check_question_intent(q)


@pytest.mark.parametrize(
    "q",
    [
        "How many employees are in Engineering?",
        "Compare Engineering and Finance headcount",
        "What is the average salary per department?",
    ],
)
def test_read_intent_allowed(q):
    check_question_intent(q)


def test_extract_sql_from_chatty_output():
    out = "Sure! Here is the query:\n```sql\nSELECT COUNT(*) FROM employees;\n```\nHope it helps"
    assert extract_sql(out) == "SELECT COUNT(*) FROM employees"


# ---------------- Response guardrails ----------------


def test_rag_answer_without_sources_is_replaced():
    answer, v = validate_response("rag", "Employees get 99 days off.", sources=[])
    assert answer == NO_ANSWER
    assert not v.passed


def test_rag_unsupported_numbers_flagged():
    evidence = "Employees with more than 5 years of service receive 25 days of paid vacation per year."
    _, ok = validate_response("rag", "You get 25 days [1].", sources=[{"source": "x"}], evidence_text=evidence)
    assert ok.checks["numbers_supported_by_sources"]
    answer, bad = validate_response("rag", "You get 30 days [1].", sources=[{"source": "x"}], evidence_text=evidence)
    assert not bad.checks["numbers_supported_by_sources"]
    assert "could not be verified" in answer


def test_sql_not_executed_fails_unless_blocked():
    _, v = validate_response("sql", "error", executed=False, blocked=False)
    assert not v.passed
    _, v = validate_response("sql", "Only read-only SQL operations are supported.", executed=False, blocked=True)
    assert v.passed


def test_unsupported_numbers_handles_formatting():
    assert unsupported_numbers("There are 1,234 people", '[{"n": 1234}]') == set()
    assert unsupported_numbers("Average is $125,432.50", '[{"avg": 125432.5}]') == set()
