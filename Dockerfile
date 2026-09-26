# syntax=docker/dockerfile:1.7
# ---------- Stage 1: build wheels ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="production-agentic-ai" \
      org.opencontainers.image.description="Agentic RAG + SQL platform (FastAPI, LangGraph, pgvector)" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_VERSION=${APP_VERSION} \
    PORT=8000 \
    WEB_CONCURRENCY=1

# Non-root user with a fixed UID so Kubernetes securityContext can pin it.
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels

COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app data/documents ./data/documents
COPY --chown=app:app data/eval ./data/eval

USER 10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)" || exit 1

# One worker per container; scale horizontally with replicas/HPA instead of in-process workers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
