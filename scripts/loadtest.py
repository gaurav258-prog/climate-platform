"""Load / capacity harness — measure latency percentiles + throughput, and check them against the SLOs.

Self-contained (asyncio + httpx, no k6/locust binary). Fires a target concurrency at one or more endpoints for
a fixed duration, then reports p50/p90/p95/p99 latency, throughput (req/s), and error rate — overall and per
endpoint — and PASS/FAILs against the SLO budget from docs/observability/slo.yaml. Fills the "no verified
throughput benchmarks" gap with an actual, reproducible number; record runs in docs/observability/CAPACITY.md.

    python -m scripts.loadtest --base-url http://localhost:8001 --paths /health --duration 10 --concurrency 25
    python -m scripts.loadtest --paths /health,/metrics --duration 20 --concurrency 50 --slo-p95 0.4 --json out.json
    # authed endpoint:  --paths /v1/... --token "$JWT"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

try:
    import httpx
except ImportError:  # pragma: no cover
    raise SystemExit("httpx is required: pip install httpx")


def _pct(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    k = max(0, min(len(sorted_ms) - 1, int(round((p / 100.0) * (len(sorted_ms) - 1)))))
    return sorted_ms[k]


async def _worker(client: httpx.AsyncClient, paths: list[str], method: str, deadline: float,
                  headers: dict, sink: list) -> None:
    i = 0
    while time.monotonic() < deadline:
        path = paths[i % len(paths)]
        i += 1
        t0 = time.monotonic()
        try:
            r = await client.request(method, path, headers=headers)
            code, ok = r.status_code, r.status_code < 500
        except Exception:  # noqa: BLE001 — a connection error is a failed request, not a crash
            code, ok = 0, False
        sink.append((path, code, ok, (time.monotonic() - t0) * 1000.0))


def _summarise(rows: list, label: str, wall_s: float, slo_p95_ms: float, slo_err: float) -> dict:
    n = len(rows)
    lat = sorted(r[3] for r in rows)
    errs = sum(1 for r in rows if not r[2])
    err_rate = (errs / n) if n else 0.0
    p95 = _pct(lat, 95)
    ok = p95 <= slo_p95_ms and err_rate <= slo_err
    return {
        "label": label, "requests": n, "rps": round(n / wall_s, 1) if wall_s else 0.0,
        "error_rate": round(err_rate, 4), "errors": errs,
        "p50_ms": round(_pct(lat, 50), 1), "p90_ms": round(_pct(lat, 90), 1),
        "p95_ms": round(p95, 1), "p99_ms": round(_pct(lat, 99), 1),
        "max_ms": round(lat[-1], 1) if lat else 0.0,
        "slo_pass": ok,
    }


async def run(args) -> dict:
    paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    sink: list = []
    start = time.monotonic()
    deadline = start + args.duration
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout, limits=limits) as client:
        await asyncio.gather(*[_worker(client, paths, args.method, deadline, headers, sink)
                               for _ in range(args.concurrency)])
    wall = time.monotonic() - start
    overall = _summarise(sink, "OVERALL", wall, args.slo_p95 * 1000, args.slo_error_rate)
    per = [_summarise([r for r in sink if r[0] == p], p, wall, args.slo_p95 * 1000, args.slo_error_rate)
           for p in paths] if len(paths) > 1 else []
    return {"config": {"base_url": args.base_url, "paths": paths, "concurrency": args.concurrency,
                       "duration_s": args.duration, "slo_p95_s": args.slo_p95},
            "wall_s": round(wall, 2), "overall": overall, "per_endpoint": per}


def _print(report: dict) -> None:
    def line(s: dict) -> str:
        flag = "PASS" if s["slo_pass"] else "FAIL"
        return (f"  {s['label']:<22} {s['requests']:>7} req  {s['rps']:>7} rps  "
                f"p50 {s['p50_ms']:>6}  p95 {s['p95_ms']:>7}  p99 {s['p99_ms']:>7} ms  "
                f"err {s['error_rate']*100:>4.1f}%  [{flag}]")
    c = report["config"]
    print(f"\nLoad test · {c['base_url']} · {c['paths']} · {c['concurrency']} conc · {c['duration_s']}s "
          f"· SLO p95 ≤ {c['slo_p95_s']}s")
    print("-" * 104)
    print(line(report["overall"]))
    for s in report["per_endpoint"]:
        print(line(s))
    print("-" * 104)
    print("VERDICT:", "PASS — within SLO" if report["overall"]["slo_pass"] else "FAIL — SLO breached")


def main() -> int:
    ap = argparse.ArgumentParser(description="Load / capacity harness")
    ap.add_argument("--base-url", default="http://localhost:8001")
    ap.add_argument("--paths", default="/health", help="comma-separated paths")
    ap.add_argument("--method", default="GET")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds")
    ap.add_argument("--concurrency", type=int, default=25)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--token", default="", help="bearer token for authed endpoints")
    ap.add_argument("--slo-p95", type=float, default=1.0, help="p95 latency budget (seconds)")
    ap.add_argument("--slo-error-rate", type=float, default=0.001)
    ap.add_argument("--json", dest="json_out", default="", help="write JSON report to this path")
    args = ap.parse_args()

    report = asyncio.run(run(args))
    _print(report)
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print("wrote", args.json_out)
    return 0 if report["overall"]["slo_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
