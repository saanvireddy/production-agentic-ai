"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, chat, documents, health
from app.config import Settings, get_settings
from app.monitoring.logging import request_id_ctx, setup_logging
from app.monitoring.metrics import ERROR_COUNT, IN_FLIGHT, REQUEST_COUNT, REQUEST_LATENCY
from app.monitoring.tracing import setup_tracing
from app.services.container import Container, build_container

logger = logging.getLogger(__name__)


def _startup_tasks(container: Container) -> None:
    from app.database.bootstrap import bootstrap

    s = container.settings
    bootstrap(container.store, container.embeddings, migrate=s.auto_migrate, seed=s.auto_seed, ingest=s.auto_ingest)


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or (container.settings if container else get_settings())
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if container is None:
            app.state.container = build_container(settings)
            _startup_tasks(app.state.container)
        else:
            app.state.container = container
        logger.info("startup complete", extra={"env": settings.environment, "llm": settings.llm_model})
        yield
        if container is None:
            from app.database.connection import close_pool

            close_pool()

    app = FastAPI(
        title="Production Agentic AI Platform",
        description="Agentic RAG + SQL assistant (LangGraph, pgvector, Ollama) with JWT auth, "
        "guardrails, evaluation and observability.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        IN_FLIGHT.inc()
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = rid
            return response
        except Exception:
            logger.exception("unhandled error")
            return JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        finally:
            route = request.scope.get("route")
            # Route *template* (e.g. /api/v1/chat/{session_id}) keeps label cardinality bounded.
            # Included routers report their path without the include prefix, so add it back.
            path = getattr(route, "path", "unmatched")
            if request.url.path.startswith(settings.api_prefix) and not path.startswith(settings.api_prefix):
                path = settings.api_prefix + path
            elapsed = time.perf_counter() - t0
            REQUEST_COUNT.labels(request.method, path, str(status)).inc()
            REQUEST_LATENCY.labels(request.method, path).observe(elapsed)
            if status >= 500:
                ERROR_COUNT.labels(path).inc()
            IN_FLIGHT.dec()
            request_id_ctx.reset(token)

    for r in (health.router, auth.router, chat.router, documents.router):
        app.include_router(r, prefix=settings.api_prefix)
    # Un-prefixed aliases for probes and Prometheus scrapers.
    app.add_api_route("/health", health.health, methods=["GET"], include_in_schema=False)
    app.add_api_route("/metrics", health.metrics, methods=["GET"], include_in_schema=False)

    setup_tracing(app)
    return app


app = create_app()  # uvicorn app.main:app
