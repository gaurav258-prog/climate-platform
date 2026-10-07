"""E173: a dropped connection costs a retry, never the run — a partial file resumes, a server that ignores the range
restarts it, and a file that keeps failing is reported against that file instead of raising."""
from __future__ import annotations

import requests

from scripts import download as dl

BODY = bytes(range(256)) * 40          # 10,240 bytes


class _Resp:
    def __init__(self, status: int, data: bytes, fail_after: int | None = None):
        self.status_code, self._data, self._fail_after = status, data, fail_after

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, n):
        sent = 0
        for i in range(0, len(self._data), 1000):
            if self._fail_after is not None and sent >= self._fail_after:
                raise requests.exceptions.SSLError("record layer failure")
            chunk = self._data[i:i + 1000]
            sent += len(chunk)
            yield chunk


def _server(monkeypatch, plan):
    calls = []

    def get(url, stream, timeout, headers):
        calls.append(headers.get("Range"))
        return plan(len(calls), headers.get("Range"))
    monkeypatch.setattr(dl.requests, "get", get)
    return calls


def test_a_dropped_connection_resumes_where_it_stopped(tmp_path, monkeypatch):
    def plan(n, rng):
        if n == 1:
            return _Resp(200, BODY, fail_after=4000)                     # drops after 4,000 bytes
        start = int(rng.split("=")[1].rstrip("-"))
        return _Resp(206, BODY[start:])
    calls = _server(monkeypatch, plan)
    out = tmp_path / "f.tif"
    assert dl.download("u", out, len(BODY), pause_s=0) == "fetched"
    assert out.read_bytes() == BODY and calls == [None, "bytes=4000-"]


def test_a_server_that_ignores_the_range_starts_the_file_again(tmp_path, monkeypatch):
    (tmp_path / "f.tif.part").write_bytes(BODY[:3000])
    _server(monkeypatch, lambda n, rng: _Resp(200, BODY))
    out = tmp_path / "f.tif"
    assert dl.download("u", out, len(BODY), pause_s=0) == "fetched" and out.read_bytes() == BODY


def test_a_file_that_keeps_failing_is_reported_not_raised(tmp_path, monkeypatch):
    calls = _server(monkeypatch, lambda n, rng: _Resp(503, b""))
    got = dl.download("u", tmp_path / "f.tif", len(BODY), attempts=3, pause_s=0)
    assert got.startswith("failed: HTTPError") and len(calls) == 3 and not (tmp_path / "f.tif").exists()


def test_a_whole_file_is_held(tmp_path, monkeypatch):
    out = tmp_path / "f.tif"
    out.write_bytes(BODY)
    calls = _server(monkeypatch, lambda n, rng: _Resp(200, BODY))
    assert dl.download("u", out, len(BODY), pause_s=0) == "held" and calls == []
