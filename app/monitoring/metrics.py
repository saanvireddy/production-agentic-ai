"""Prometheus metrics. Exposed at GET /api/v1/metrics (and /metrics for scrapers)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---- HTTP ----
REQUEST_COUNT = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
IN_FLIGHT = Gauge("http_requests_in_flight", "Requests currently being served")
ERROR_COUNT = Counter("http_errors_total", "HTTP 5xx responses", ["path"])

# ---- Agent ----
AGENT_ROUTE = Counter("agent_route_total", "Router decisions", ["route", "method"])
AGENT_LATENCY = Histogram(
    "agent_duration_seconds",
    "End-to-end agent latency",
    ["route"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80),
)
GUARDRAIL_BLOCKS = Counter("guardrail_blocks_total", "Guardrail interventions", ["guardrail", "reason"])

# ---- LLM ----
LLM_REQUESTS = Counter("llm_requests_total", "LLM calls", ["task", "status"])
LLM_LATENCY = Histogram(
    "llm_request_duration_seconds",
    "LLM call latency",
    ["task"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80),
)

# ---- Tools ----
RAG_REQUESTS = Counter("rag_requests_total", "RAG tool invocations", ["outcome"])
RAG_RETRIEVAL_SCORE = Histogram(
    "rag_top_score",
    "Cosine similarity of the best retrieved chunk",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
SQL_QUERIES = Counter("sql_queries_total", "SQL tool invocations", ["outcome"])
SQL_LATENCY = Histogram(
    "sql_query_duration_seconds", "SQL execution latency", buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 5)
)

# ---- Platform ----
CACHE_HITS = Counter("cache_hits_total", "Answer cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Answer cache misses")
RATE_LIMITED = Counter("rate_limited_total", "Requests rejected by the rate limiter")
DOCUMENTS_INGESTED = Counter("documents_ingested_total", "Documents ingested")
