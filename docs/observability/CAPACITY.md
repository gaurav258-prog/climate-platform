# Capacity & load benchmarks

Fills the "no verified throughput benchmarks" gap with reproducible numbers. The harness
(`scripts/loadtest.py`) is self-contained (asyncio + httpx — no k6/locust binary), measures latency
percentiles + throughput + error rate, and PASS/FAILs against the SLO budget in [`slo.yaml`](./slo.yaml).

## How to run

```bash
# unauthenticated smoke (safe to hammer)
python -m scripts.loadtest --base-url http://localhost:8001 --paths /health,/metrics \
    --duration 20 --concurrency 50 --slo-p95 0.4 --json out.json

# an authed read endpoint
python -m scripts.loadtest --paths /v1/... --token "$JWT" --duration 30 --concurrency 100
```

Exit code is non-zero on an SLO breach, so it can gate a release in CI (against a staging target).

## What it checks (from slo.yaml)

- **Latency** — p95 within the budget (`--slo-p95`, default 1.0s; API-read target **0.4s**).
- **Error rate** — ≤ 0.1% (`--slo-error-rate`).
- Reports p50 / p90 / p95 / p99, throughput (req/s), error rate — overall and per endpoint.

## Recorded runs

> Baselines only — a **dev box** running the API single-process under `uvicorn --reload` (worst case).
> Production (multiple workers, no reload, tuned Postgres pool) is materially faster. Re-run on staging
> before quoting a capacity number externally.

| Date | Target | Endpoints | Conc | Dur | RPS | p50 | p95 | p99 | Err | SLO |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-28 | dev `:8001` (reload) | /health, /metrics | 25 | 8s | **260** | 61ms | 286ms | 457ms | 0.0% | PASS (p95≤400ms) |

## Next (to reach a defensible published capacity figure)

- Run on **staging** with the production process model (gunicorn/uvicorn workers ×N, no reload).
- Include an **authed read** and a representative **any-address score** path (interactive SLO p95 < 3s).
- Sweep concurrency (25 → 100 → 250) to find the knee; record the RPS/p95 curve here.
- Add a **DB-pool + Postgres** view (connections, slow queries) during the run to locate the first chokepoint.
- Wire a nightly staging run so the curve is tracked over time, not measured once.
