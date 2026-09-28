"""The volcano catalogue is rewritten only when its data changes — a check that finds the same data leaves the
committed file untouched (the check itself is logged by the feed monitor)."""
import json

import scripts.fetch_gvp_catalogue as G


def _fake(monkeypatch, n):
    vols = [{"volcano_number": i, "name": f"V{i}"} for i in range(n)]
    monkeypatch.setattr(G, "_wfs_all", lambda layer, timeout=180: [])
    monkeypatch.setattr(G, "build_catalogue", lambda v, e: {"source": "s", "fetched_at": f"t{n}-{len(calls)}", "n_volcanoes": n,
                                                             "volcanoes": vols})


calls: list = []


def test_same_data_is_not_rewritten_changed_data_is(tmp_path, monkeypatch):
    out = tmp_path / "gvp.json"
    _fake(monkeypatch, 1200)
    first = G.refresh(out)
    assert first["changed"] is True
    before = out.read_text()
    calls.append(1)                                           # a later check: new fetch time, same data
    again = G.refresh(out)
    assert again["changed"] is False and out.read_text() == before
    assert json.loads(before)["fetched_at"] == again["fetched_at"]    # the version time stays the first fetch
    _fake(monkeypatch, 1201)                                  # the source really changed
    assert G.refresh(out)["changed"] is True and json.loads(out.read_text())["n_volcanoes"] == 1201
