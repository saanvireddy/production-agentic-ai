from app.database.seed import generate_employees


def test_health(client):
    for path in ("/health", "/api/v1/health"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


def test_readiness(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["postgres"] == "ok"


def test_chat_sql(client, user_headers):
    r = client.post("/api/v1/chat", headers=user_headers, json={"question": "How many employees are in Engineering?"})
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "sql"
    assert body["rows"][0]["headcount"] == sum(1 for e in generate_employees() if e[1] == "Engineering")
    assert body["sources"][0]["source"] == "employee database"
    assert r.headers["x-ratelimit-limit"]


def test_chat_rag_with_citations(client, user_headers):
    r = client.post(
        "/api/v1/chat", headers=user_headers, json={"question": "What is the company's remote work policy?"}
    )
    body = r.json()
    assert body["route"] == "rag"
    assert body["sources"][0]["source"] == "remote_work_policy.pdf"
    assert body["sources"][0]["page"] is not None


def test_chat_memory_across_turns(client, user_headers):
    first = client.post(
        "/api/v1/chat", headers=user_headers, json={"question": "How many employees are in Engineering?"}
    ).json()
    second = client.post(
        "/api/v1/chat",
        headers=user_headers,
        json={"question": "What about Finance?", "session_id": first["session_id"]},
    ).json()
    assert second["standalone_question"] == "How many employees are in Finance?"
    assert second["rows"][0]["department"] == "Finance"
    hist = client.get(f"/api/v1/chat/{first['session_id']}/history", headers=user_headers).json()
    assert len(hist) == 4


def test_sessions_are_isolated_between_users(client, user_headers, admin_headers):
    sid = client.post("/api/v1/chat", headers=user_headers, json={"question": "Hello!"}).json()["session_id"]
    assert client.get(f"/api/v1/chat/{sid}/history", headers=admin_headers).json() == []


def test_chat_cache_hit(client, user_headers):
    q = {"question": "What is the minimum password length?"}
    assert client.post("/api/v1/chat", headers=user_headers, json=q).json()["cached"] is False
    assert client.post("/api/v1/chat", headers=user_headers, json=q).json()["cached"] is True


def test_chat_validation_errors(client, user_headers):
    assert client.post("/api/v1/chat", headers=user_headers, json={"question": "   "}).status_code == 422
    assert client.post("/api/v1/chat", headers=user_headers, json={"question": "x" * 5000}).status_code == 422
    assert (
        client.post(
            "/api/v1/chat", headers=user_headers, json={"question": "hi", "session_id": "../../etc"}
        ).status_code
        == 422
    )


def test_rate_limit(client, user_headers, container):
    container.rate_limiter.limit = 2
    codes = [
        client.post("/api/v1/chat", headers=user_headers, json={"question": "Hello!"}).status_code for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_documents_upload_and_list(client, admin_headers, user_headers):
    r = client.post(
        "/api/v1/documents",
        headers=admin_headers,
        files={"file": ("parking_policy.md", b"# Parking Policy\n\nLot B is free for staff.", "text/markdown")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ingested"
    names = [d["filename"] for d in client.get("/api/v1/documents", headers=user_headers).json()]
    assert "parking_policy.md" in names and "leave_policy.pdf" in names
    assert client.delete("/api/v1/documents/parking_policy.md", headers=admin_headers).status_code == 204


def test_metrics_exposed(client, user_headers):
    client.post("/api/v1/chat", headers=user_headers, json={"question": "How many employees are in Sales?"})
    text = client.get("/metrics").text
    assert "http_requests_total" in text
    assert 'agent_route_total{method="heuristic",route="sql"}' in text
    assert "llm_request_duration_seconds" in text


def test_metric_path_label_is_full_route_template(client, user_headers):
    client.get("/api/v1/chat/abc-123/history", headers=user_headers)
    text = client.get("/metrics").text
    assert 'path="/api/v1/chat/{session_id}/history"' in text
    assert 'path="/api/v1/chat/abc-123/history"' not in text
