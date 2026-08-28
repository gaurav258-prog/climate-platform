# On-call runbook — Tellumen platform

Operational guide for the platform on-call. Pairs with [`slo.yaml`](./slo.yaml) (the targets) and the
telemetry emitted by `api/observability.py`.

## What we emit

| Signal | Where | Notes |
|---|---|---|
| **Metrics** | `GET /metrics` (Prometheus) | `http_requests_total`, `http_request_duration_seconds` (histogram), `http_slo_events_total{sli,outcome}` |
| **Traces** | OTLP → collector | OpenTelemetry; on only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and the `otel` extra is installed. FastAPI + SQLAlchemy + HTTPX auto-instrumented |
| **Logs** | stdout (JSON) | one access line per request; carries `trace_id` when tracing is live, so a log links to its trace |
| **Errors** | Sentry | on only when `SENTRY_DSN` is set |

Enable tracing in an environment:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
pip install -e ".[otel]"     # or [all]
```

## SLOs & error budget

Targets live in `slo.yaml`. Compute compliance and burn from `/metrics`:

```
availability = good / (good + bad)   over http_slo_events_total{sli="availability"}
latency      = good / (good + bad)   over http_slo_events_total{sli="latency"}
error_budget_remaining = 1 - (1 - availability) / (1 - 0.999)
```

**Alerting (recommended multi-window burn):**
- **Page** — fast burn: availability SLI over 5m *and* 1h both burning >14.4× budget.
- **Ticket** — slow burn: over 6h burning >6× budget.
- **Page** — latency SLO compliance < objective for 15m, or p95 `any_address_score` > 6s for 10m.

When the **error budget is exhausted**, freeze non-critical releases until it recovers (`release_policy.error_budget_freeze`).

## Filing-window posture

During declared **CSRD / SFDR / EUDR / Pillar 3** deadlines the cost of an outage is materially higher:
- **Change-freeze** — no non-critical deploys.
- Availability objective tightens to **99.95%**, **RTO 1h**.
- On-call is primed; escalation times halved.

## Common incidents

| Symptom | First checks | Likely cause / action |
|---|---|---|
| 5xx spike (availability burn) | recent deploy? DB reachable? `/metrics` status breakdown | roll back last release; check Postgres connections/locks; verify `DATABASE_URL` |
| Latency SLO burn | slow endpoint via trace waterfall; DB slow queries | check N+1 / missing index via SQLAlchemy spans; scale API replicas; inspect Redis/Celery backlog |
| Async hazard jobs stalled | Celery worker up? Redis reachable? external CDS/FIRMS status | provider-latency-bound — communicate, don't page unless queue unbounded; restart worker if crashed |
| Data-integrity alarm | is a write hitting an append-only table? | canonical scores + report snapshots are append-only by design — investigate the writer, never mutate |
| Golden-source feed overdue | Control Center → data readiness; beat schedule | refresh before any filing; overdue basis feed blocks a defensible filing |

## Recovery objectives (see slo.yaml)

- **RTO** 4h (1h in a filing window) · **RPO** ≤15m general, **≤5m** for canonical scores + filed snapshots.
- Golden source is append-only → recovery restores from continuous WAL/replica; **never** replay mutations.

## Escalation

1. Platform on-call (page).  2. Eng lead.  3. CTO — for data-integrity, security, or a filing-window outage.
Security incident → follow the security runbook and preserve the audit trail (do not prune).
