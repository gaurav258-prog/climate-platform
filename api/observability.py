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
_log = logging.getLogger("api.access")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            _REQUESTS.labels(request.method, "500").inc()
            raise
        dur = time.time() - start
        _REQUESTS.labels(request.method, str(status)).inc()
        _LATENCY.labels(request.method).observe(dur)
        _log.info(json.dumps({
            "method": request.method, "path": request.url.path, "status": status,
            "dur_ms": round(dur * 1000, 1),
        }))
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
