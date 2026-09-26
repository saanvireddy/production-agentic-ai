from app.database.seed import generate_employees
from app.services.llm import DeterministicFakeLLM
from app.sql.tool import SqlTool


def _expected_count(dept: str) -> int:
    return sum(1 for r in generate_employees() if r[1] == dept)


def test_sql_tool_counts_engineering(sql_executor):
    res = SqlTool(DeterministicFakeLLM(), sql_executor).run("How many employees are in Engineering?")
    assert res.executed
    assert res.rows == [{"department": "Engineering", "headcount": _expected_count("Engineering")}]
    assert str(_expected_count("Engineering")) in res.answer
    assert "LIMIT" in res.sql


def test_sql_tool_blocks_destructive_question(sql_executor):
    res = SqlTool(DeterministicFakeLLM(), sql_executor).run("Delete all employees")
    assert not res.executed
    assert res.answer == "Only read-only SQL operations are supported."
    assert sql_executor.executed == []  # nothing reached the database


def test_sql_tool_blocks_malicious_llm_output(sql_executor):
    class EvilLLM(DeterministicFakeLLM):
        @staticmethod
        def _respond(prompt: str) -> str:
            return "SELECT * FROM employees; DROP TABLE employees;"

    res = SqlTool(EvilLLM(), sql_executor).run("How many employees are there?")
    assert not res.executed
    assert res.blocked_reason == "multiple_statements"
    assert sql_executor.executed == []


def test_seed_data_is_deterministic():
    assert generate_employees() == generate_employees()
    assert len(generate_employees()) == 137
