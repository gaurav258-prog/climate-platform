"""The volcano catalogue refresh lands a LIVE copy (gitignored) and never writes the committed snapshot (E114); it
writes only when the data changes — a check that finds the same data leaves every file untouched (the check itself
is logged by the feed monitor). The scorer reads the live copy when one has landed, else the snapshot."""
import json

import pytest

import ml.scoring.volcanic_point as VP
import scripts.fetch_gvp_catalogue as G
from core import live_data
from core.config import settings

calls: list = []


def _fake(monkeypatch, n):
    vols = [{"volcano_number": i, "name": f"V{i}"} for i in range(n)]
    monkeypatch.setattr(G, "_wfs_all", lambda layer, timeout=180: [])
    monkeypatch.setattr(G, "build_catalogue", lambda v, e: {"source": "s", "fetched_at": f"t{n}-{len(calls)}", "n_volcanoes": n,
                                                             "volcanoes": vols})


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_DATA_PATH", str(tmp_path / "live"))
    return tmp_path / "live"


def test_refresh_lands_live_copy_and_never_touches_the_snapshot(live, monkeypatch):
    snap = G.SNAPSHOT_PATH
    snap_before = snap.read_bytes() if snap.exists() else None
    out = live / "reference" / snap.name
    _fake(monkeypatch, 1200)
    first = G.refresh()
    assert first["changed"] is True and first["path"] == str(out) and out.exists()
    before = out.read_text()
    calls.append(1)                                           # a later check: new fetch time, same data
    again = G.refresh()
    assert again["changed"] is False and out.read_text() == before
    assert json.loads(before)["fetched_at"] == again["fetched_at"]    # the version time stays the first fetch
    _fake(monkeypatch, 1201)                                  # the source really changed
    assert G.refresh()["changed"] is True and json.loads(out.read_text())["n_volcanoes"] == 1201
    assert (snap.read_bytes() if snap.exists() else None) == snap_before   # the committed snapshot is untouched


def test_scorer_prefers_the_live_copy_and_falls_back_to_the_snapshot(live, monkeypatch):
    if not G.SNAPSHOT_PATH.exists():
        pytest.skip("GVP snapshot not committed")
    assert VP._load_catalogue()["fetched_at"] == json.loads(G.SNAPSHOT_PATH.read_text())["fetched_at"]
    _fake(monkeypatch, 1200)
    landed = G.refresh()
    assert VP._load_catalogue()["fetched_at"] == landed["fetched_at"]   # the live copy reaches a running process
    live_data.live_path(G.SNAPSHOT_PATH).unlink()
    assert VP._load_catalogue()["n_volcanoes"] == json.loads(G.SNAPSHOT_PATH.read_text())["n_volcanoes"]


def test_promote_is_the_only_way_to_change_the_snapshot(live, tmp_path, monkeypatch):
    snap = tmp_path / "data" / "reference" / "x.json"         # a stand-in snapshot outside the repository
    monkeypatch.setattr(live_data, "REPO_ROOT", tmp_path)
    snap.parent.mkdir(parents=True)
    snap.write_text("old")
    with pytest.raises(FileNotFoundError):
        live_data.promote(snap)
    live_data.write_live(snap, "new")
    assert snap.read_text() == "old"
    live_data.promote(snap)
    assert snap.read_text() == "new"
