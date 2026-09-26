"""OpenTelemetry tracing.

When OTEL_ENABLED=true, spans are exported over OTLP/gRPC (to Jaeger locally, or an
OTel Collector -> X-Ray/CloudWatch in AWS). When disabled, the OTel API is a no-op, so
`tracer.start_as_current_span(...)` calls throughout the code cost ~nothing.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry import trace

from app.config import get_settings

logger = logging.getLogger(__name__)

tracer = trace.get_tracer("agentic-ai")


def setup_tracing(app: FastAPI) -> None:
    s = get_settings()
    if not s.otel_enabled:
        return
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": s.otel_service_name,
                "deployment.environment": s.environment,
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=s.otel_exporter_endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    logger.info("OpenTelemetry tracing enabled -> %s", s.otel_exporter_endpoint)
