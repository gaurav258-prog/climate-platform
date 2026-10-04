"""E164: the supply outlook reads only published calibrations, shows a range only where its gate passed, never reads a
season in progress through the fit, and is never an input to volume at risk, COGS-at-risk, KRIs or filings."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.outlook import engine as O

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
RUN = {"n_years": 31, "slope": -0.5, "intercept": 25.0, "rmse": 6.0, "score_mean": 50.0, "score_sxx": 20000.0,
       "r2_oos": 0.45, "downside_pass": True, "upside_pass": False, "upside": {"failed": ["2 band"]}}


def test_a_range_shows_only_where_its_gate_passed():
    loss = O.read_season(RUN, 80.0)                          # mid = -15: a loss, downside passed
    assert loss["reads"] == "loss" and loss["range_pct"][1] == -15.0
    gain = O.read_season(RUN, 20.0)                          # mid = +15: a gain, upside not passed → held
    assert gain["reads"] == "held" and "upside rules did not pass (2 band)" in gain["why"]
    up = O.read_season({**RUN, "upside_pass": True, "upside": {"capped": False}}, 20.0)
    assert up["reads"] == "gain" and up["range_pct"][1] == 15.0
    capped = O.read_season({**RUN, "upside_pass": True,
                            "upside": {"capped": True, "capped_line": {"wet_cap_pct": 9.0}}}, 20.0)
    assert capped["range_pct"][1] == 9.0 and capped["capped"]
    held = O.read_season({**RUN, "downside_pass": False}, 80.0)
    assert held["reads"] == "held" and "downside gate" in held["why"]


def test_no_risk_figure_reads_the_outlook():
    """Volume at risk, COGS-at-risk, KRIs and filings never import the outlook — it is context, not a risk input."""
    allowed = {ROOT / "api/routers/supply.py"}
    imports = re.compile(r"(from\s+services\.outlook|import\s+services\.outlook)")
    offenders = [str(p.relative_to(ROOT)) for d in ("services", "api", "ml") for p in (ROOT / d).rglob("*.py")
                 if imports.search(p.read_text(encoding="utf-8")) and p not in allowed
                 and "services/outlook" not in str(p)]
    assert offenders == []


def _built(box: str) -> bool:
    from core.db.config import SessionLocal
    from services.calibration import crop_weather
    try:
        with SessionLocal() as s:
            return crop_weather.latest(s, crop_weather.box_target(box)) is not None
    except Exception:
        return False


@pytest.mark.skipif(not _built("spain_olive"), reason="no weather build holds the olive box on this machine")
def test_the_outlook_reads_published_runs_and_the_seasons_beyond_the_record(session_rolled_back):
    """A published olive run: its origin listed (own when the org sources there), each season after the yield record
    read through the fit or held, never a season in progress."""
    from sqlalchemy import text

    from services.calibration import publish, runner, specs
    s = session_rolled_back
    s.execute(text("UPDATE crop_calibration_specs SET retired_at = now(), retired_reason = 'test' "
                   "WHERE commodity = 'Olive oil' AND origin = 'ES' AND driver = 'drought' AND retired_at IS NULL"))
    sid = specs.create(s, commodity="Olive oil", origin="ES", yield_source="FAOSTAT QCL bulk", driver="drought",
                       weather_kind="box", weather_key="spain_olive", season_months=[4, 5, 6, 7, 8], allow_cycle=True,
                       basis="test recipe (E164)", protocol="crop-calib-v1")
    r = runner.run(s, runner.spec(s, sid))
    publish.propose(s, [r["run_id"]], "test (E164)")
    from services.governance.platform_policy import SYSTEM_USER
    publish.apply_decision(s, {"run_ids": [r["run_id"]]}, "approved", SYSTEM_USER, "test")
    out = O.outlook(s, "Olive oil", ["ES"])
    es = next(o for o in out["origins"] if o["origin"] == "ES" and o["driver"] == "drought")
    assert es["own"] and es["downside_pass"] and es["last_reported_year"] >= 2024
    for season in es["seasons"]:
        assert season["year"] > es["last_reported_year"] and season["reads"] in ("loss", "gain", "held")
        assert ("range_pct" in season) == (season["reads"] != "held")
    if es["in_progress"]:
        assert es["in_progress"]["year"] not in {x["year"] for x in es["seasons"]}
