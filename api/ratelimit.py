"""Lightweight per-IP rate limiting for sensitive endpoints (login, password reset).

An in-process sliding window — defense-in-depth on top of the per-account DB lockout. It resets on restart and
is per-worker, so a multi-worker or multi-instance deployment should front this with a shared store (Redis) or an
edge WAF; the dependency factory is the seam to swap the backend without touching call sites.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_BUCKETS: list[dict] = []          # every limiter's window, so a test run can start each test from a clean slate


def reset() -> None:
    """Clear every limiter's window (tests: one process plays every client from one address)."""
    for b in _BUCKETS:
        b.clear()


def rate_limiter(max_calls: int, window_seconds: int):
    bucket: dict[str, deque] = defaultdict(deque)
    _BUCKETS.append(bucket)

    def dep(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        dq = bucket[ip]
        while dq and dq[0] <= now - window_seconds:
            dq.popleft()
        if len(dq) >= max_calls:
            raise HTTPException(status_code=429,
                                detail={"error": "rate_limited", "message": "Too many attempts. Please wait a moment and try again."})
        dq.append(now)

    return dep
