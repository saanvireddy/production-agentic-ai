from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import get_container
from app.api.schemas import HealthResponse
from app.services.container import Container

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness probe")
def ready(response: Response, container: Container = Depends(get_container)) -> HealthResponse:
    s = container.settings
    checks: dict[str, str] = {}

    checks["postgres"] = "ok" if container.db_ping() else "down"
    try:
        container.memory.r.ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "degraded"  # app still works without Redis
    if s.llm_provider == "ollama":
        try:
            httpx.get(f"{s.ollama_url}/api/tags", timeout=2).raise_for_status()
            checks["ollama"] = "ok"
        except Exception:  # noqa: BLE001
            checks["ollama"] = "down"
    else:
        checks["ollama"] = "skipped (fake llm)"

    # Only Postgres gates readiness. An Ollama outage should page someone (see the LLMErrors alert),
    # not pull every pod out of the Service - SQL/document endpoints still work without it.
    healthy = checks["postgres"] == "ok"
    if not healthy:
        response.status_code = 503
    return HealthResponse(status="ready" if healthy else "not_ready", checks=checks)


@router.get("/metrics", include_in_schema=True, summary="Prometheus metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
