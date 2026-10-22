"""E309: the Copernicus Data Stores refuse a job when too many are queued for one dataset ('Maximum number queued
requests for this dataset has been reached. Please configure your scripts to request data sequentially'); two address
lookups were enough. Requests to one dataset now go one at a time, the refusal is retried, and a request still refused
ends as CopernicusBusy — never an unexpected error."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest

from services.data import copernicus as C

ROOT = Path(__file__).resolve().parents[2]
BUSY = RuntimeError("400 Client Error: The job has been rejected\nMaximum number queued requests for this dataset has "
                    "been reached. Please configure your scripts to request data sequentially")


@pytest.fixture(autouse=True)
def _locks(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LOCK_DIR", str(tmp_path))


class _Client:
    def __init__(self, fail=(), hold=0.0):
        self.calls, self.fail, self.hold = 0, list(fail), hold
        self.active = self.peak = 0
        self.lock = threading.Lock()

    def retrieve(self, dataset, request, target):
        with self.lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.hold)
            if self.fail:
                raise self.fail.pop(0)
        finally:
            with self.lock:
                self.active -= 1


def _run(client, datasets):
    ts = [threading.Thread(target=C.retrieve, args=(client, "cds", d, {}, "/dev/null")) for d in datasets]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


def test_requests_to_one_dataset_go_one_at_a_time():
    c = _Client(hold=0.15)
    _run(c, ["reanalysis-era5-land"] * 3)
    assert c.calls == 3 and c.peak == 1


def test_requests_to_different_datasets_may_run_together():
    c = _Client(hold=0.3)
    _run(c, ["reanalysis-era5-land", "cams-global-atmospheric-composition-forecasts"])
    assert c.peak == 2


def test_a_refusal_is_retried_after_a_wait():
    c, waited = _Client(fail=[BUSY]), []
    C.retrieve(c, "ads", "cams", {}, "/dev/null", waits=(30, 60), sleep=waited.append)
    assert c.calls == 2 and waited == [30]


def test_a_request_still_refused_ends_busy_not_failed():
    c, waited = _Client(fail=[BUSY, BUSY, BUSY]), []
    with pytest.raises(C.CopernicusBusy):
        C.retrieve(c, "cds", "era5", {}, "/dev/null", waits=(1, 2), sleep=waited.append)
    assert c.calls == 3 and waited == [1, 2]


def test_any_other_error_is_the_callers_unretried():
    c = _Client(fail=[ValueError("MultiAdaptorNoDataError")])
    with pytest.raises(ValueError):
        C.retrieve(c, "cds", "era5", {}, "/dev/null", sleep=lambda s: None)
    assert c.calls == 1


def test_no_turn_in_time_ends_busy():
    with C._turn("cds", "era5", 5, time.sleep):
        with pytest.raises(C.CopernicusBusy):
            C.retrieve(_Client(), "cds", "era5", {}, "/dev/null", lock_wait_s=0.6, sleep=time.sleep)


def test_code_that_runs_in_the_platform_reaches_copernicus_only_through_the_one_door():
    stray = []
    for top in ("api", "services", "ml", "core"):
        for f in (ROOT / top).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            src = f.read_text(encoding="utf-8", errors="ignore")
            if rel != "services/data/copernicus.py" and "cdsapi" in src and re.search(r"(?<!copernicus)\.retrieve\(", src):
                stray.append(rel)
    assert stray == [], f"call Copernicus through services.data.copernicus.retrieve: {stray}"
