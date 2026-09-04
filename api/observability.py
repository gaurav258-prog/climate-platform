"""Observability — Prometheus metrics, structured access logs, and optional Sentry error tracking.

A request middleware records a request counter + latency histogram (labelled by method and status only, to
keep cardinality bounded) and emits one JSON access-log line per request. `/metrics` exposes the Prometheus
exposition format. Sentry initialises only when a DSN is configured and the SDK is installed — otherwise it is a
no-op, so error tracking is an env-gated switch, not a hard dependency.
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings

_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "status"])
_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method"])
# SLO service-level indicators: one good/bad event per request per SLI, so a dashboard can compute
# SLO compliance and an error budget directly from /metrics. `availability`: bad on a 5xx.
# `latency`: bad when the request is slower than SLO_LATENCY_BUDGET_S. See docs/observability/slo.yaml.
_SLO = Counter("http_slo_events_total", "SLO good/bad events", ["sli", "outcome"])
_log = logging.getLogger("api.access")


def _current_trace_id() -> str | None:
    """Active OTel trace id (32-hex) if tracing is running, else None — lets logs join traces."""
    try:
        from opentelemetry import trace
        ctx = trace.get_current_span().get_span_context()
        if getattr(ctx, "is_valid", False):
            return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001 — logging must never fail on a tracing hiccup
        pass
    return None


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            _REQUESTS.labels(request.method, "500").inc()
            _SLO.labels("availability", "bad").inc()
            raise
        dur = time.time() - start
        _REQUESTS.labels(request.method, str(status)).inc()
        _LATENCY.labels(request.method).observe(dur)
        # SLI outcomes — the raw material for SLO compliance + error budget
        _SLO.labels("availability", "bad" if status >= 500 else "good").inc()
        _SLO.labels("latency", "bad" if dur > settings.SLO_LATENCY_BUDGET_S else "good").inc()
        entry = {
            "method": request.method, "path": request.url.path, "status": status,
            "dur_ms": round(dur * 1000, 1),
        }
        tid = _current_trace_id()
        if tid:
            entry["trace_id"] = tid
        _log.info(json.dumps(entry))
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security response headers (HSTS, no-sniff, framing, referrer, permissions)."""

    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def init_tracing(app=None) -> bool:
    """Set up OpenTelemetry distributed tracing — env-gated and dependency-tolerant.

    A TracerProvider is always installed (so manual spans + trace-id log correlation work with only the
    OTel SDK present). Span EXPORT is added only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and the OTLP
    exporter is installed; FastAPI / SQLAlchemy / HTTPX auto-instrumentation is applied only where the
    matching `opentelemetry-instrumentation-*` package is installed. Every optional piece is guarded, so a
    missing extra degrades to "no traces exported", never a startup failure. Returns True if export is live.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
    except Exception:  # noqa: BLE001 — SDK absent: tracing simply off
        return False

    resource = Resource.create({
        "service.name": settings.OTEL_SERVICE_NAME,
        "deployment.environment": getattr(settings, "APP_ENV", "production"),
    })
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    exporting = False
    endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or ""
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
            exporting = True
        except Exception:  # noqa: BLE001 — exporter extra not installed / bad endpoint
            logging.getLogger("api.observability").info(
                "OTLP endpoint set but exporter unavailable — traces not exported")

    # Auto-instrument whatever is installed; each is independent and optional.
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
        except Exception:  # noqa: BLE001
            pass
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from core.db.config import engine as _engine
        SQLAlchemyInstrumentor().instrument(engine=_engine)
    except Exception:  # noqa: BLE001
        pass
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception:  # noqa: BLE001
        pass
    return exporting


def init_sentry() -> bool:
    dsn = getattr(settings, "SENTRY_DSN", "") or ""
    if not dsn:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1, environment=getattr(settings, "APP_ENV", "production"))
        return True
    except Exception:  # noqa: BLE001 — error tracking must never break startup
        return False
