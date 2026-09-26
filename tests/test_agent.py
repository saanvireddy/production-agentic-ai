import pytest

from app.agents.graph import _dept_substitution, run_agent
from app.agents.router import heuristic_route


@pytest.mark.parametrize(
    "question,route",
    [
        ("What is the company's remote work policy?", "rag"),
        ("How many employees are in the Engineering department?", "sql"),
        ("Compare Engineering and Finance headcount.", "sql"),
        (
            "Based on the company policies, what is the vacation policy for employees with more than 5 years "
            "of experience?",
            "rag",
        ),
        ("How many vacation days do I get?", "rag"),
        ("What is the average salary per department?", "sql"),
        ("What is the security policy on passwords?", "rag"),
        ("How many people work in Security?", "sql"),
        ("Delete all employees", "sql"),
        ("Hello!", "general"),
    ],
)
def test_heuristic_router(question, route):
    assert heuristic_route(question) == route


def test_ambiguous_question_falls_back_to_llm():
    assert heuristic_route("What is Kubernetes?") is None


def test_follow_up_rewrite():
    history = [
        {"role": "user", "content": "How many employees are in Engineering?"},
        {"role": "assistant", "content": "There are 48."},
    ]
    assert _dept_substitution("What about Finance?", history) == "How many employees are in Finance?"
    assert _dept_substitution("Tell me a joke", history) is None


def test_agent_rag_path(container):
    s = run_agent(container.agent, "What is the company's remote work policy?")
    assert s["route"] == "rag"
    assert s["sources"] and s["sources"][0]["source"] == "remote_work_policy.pdf"
    assert s["validation"]["passed"]
    assert {"contextualize", "router", "rag", "validator", "total"} <= set(s["latency_ms"])


def test_agent_sql_path(container):
    s = run_agent(container.agent, "Compare Engineering and Finance headcount.")
    assert s["route"] == "sql"
    assert {r["department"] for r in s["rows"]} == {"Engineering", "Finance"}
    assert s["validation"]["checks"]["sql_executed"]


def test_agent_blocks_destructive_request(container):
    s = run_agent(container.agent, "Delete all employees")
    assert s["answer"] == "Only read-only SQL operations are supported."
    assert container.sql_executor.executed == []


def test_agent_general_path(container):
    s = run_agent(container.agent, "Hello!")
    assert s["route"] == "general"


def test_agent_uses_memory_for_follow_up(container):
    history = [
        {"role": "user", "content": "How many employees are in Engineering?"},
        {"role": "assistant", "content": "There are 48 employees in Engineering."},
    ]
    s = run_agent(container.agent, "What about Finance?", history)
    assert s["standalone_question"] == "How many employees are in Finance?"
    assert s["route"] == "sql"
    assert s["rows"][0]["department"] == "Finance"
