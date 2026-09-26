"""Load test for the API.

    # 10 / 50 / 100 users, 2 minutes each, CSV + HTML report
    for u in 10 50 100; do
      locust -f scripts/locustfile.py --host http://localhost:8000 --headless \
             -u $u -r 10 -t 2m --csv reports/load_${u}u --html reports/load_${u}u.html
    done

Tips:
* A local LLM serves roughly one generation at a time, so /chat throughput is bounded by
  Ollama, not FastAPI. Run once with LLM_PROVIDER=fake to measure the platform itself, and
  once with Ollama to measure the end-to-end system.
* The rate limiter (RATE_LIMIT_PER_MINUTE) will reject a single user hammering the API;
  raise it for load tests or create more users.
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, task

USERNAME = os.getenv("LOAD_USERNAME", "admin")
PASSWORD = os.getenv("LOAD_PASSWORD", "admin123")

RAG_QUESTIONS = [
    "What is the company's remote work policy?",
    "How many unused vacation days can be carried over?",
    "What is the 401(k) company match?",
    "What is the minimum password length?",
]
SQL_QUESTIONS = [
    "How many employees are in Engineering?",
    "Compare Engineering and Finance headcount.",
    "What is the average salary per department?",
    "How many employees are in Sales?",
]


class ApiUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        r = self.client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        self.session_id = str(uuid.uuid4())

    @task(1)
    def health(self) -> None:
        self.client.get("/api/v1/health", name="/health")

    @task(4)
    def rag_question(self) -> None:
        self.client.post(
            "/api/v1/chat", headers=self.headers, name="/chat [rag]", json={"question": random.choice(RAG_QUESTIONS)}
        )

    @task(4)
    def sql_question(self) -> None:
        self.client.post(
            "/api/v1/chat", headers=self.headers, name="/chat [sql]", json={"question": random.choice(SQL_QUESTIONS)}
        )

    @task(1)
    def follow_up(self) -> None:
        self.client.post(
            "/api/v1/chat",
            headers=self.headers,
            name="/chat [follow-up]",
            json={"question": "How many employees are in Marketing?", "session_id": self.session_id},
        )
        self.client.post(
            "/api/v1/chat",
            headers=self.headers,
            name="/chat [follow-up]",
            json={"question": "What about Security?", "session_id": self.session_id},
        )
