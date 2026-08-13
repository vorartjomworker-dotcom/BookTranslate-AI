from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings
from app.db import engine

_configured_services: set[str] = set()


def _headers() -> dict[str, str] | None:
    value = settings.otel_exporter_otlp_headers
    if not value:
        return None
    result: dict[str, str] = {}
    for item in value.split(","):
        key, sep, val = item.partition("=")
        if sep and key.strip():
            result[key.strip()] = val.strip()
    return result or None


def configure_tracing(*, service_name: str | None = None, app: FastAPI | None = None) -> None:
    if not settings.otel_enabled:
        return
    name = service_name or settings.otel_service_name
    if name not in _configured_services:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": name,
                    "deployment.environment": settings.app_environment,
                }
            )
        )
        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=_headers())))
        trace.set_tracer_provider(provider)
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        _configured_services.add(name)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")
