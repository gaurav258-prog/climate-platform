"""Model validation (UI standard, 2026-10-16): the page reads in one call; every figure on it comes from the data. Three
defects found in the rebuild are held here:
  * the coverage list was typed by hand and contradicted the hazard register (flood, wildfire, sea-level rise "not yet";
    seismic "validated"; heat and soil water "validated" on drought's passes) — now every hazard's standing is the
    register's tier, and its tests are the validation record's counts;
  * the cyclone check counted track positions as storms — now each storm counts once;
  * Model risk read a Spearman back out of a coverage sentence — it now reads the register and the record.
Rolled back throughout."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core import messages
from core.hazard_taxonomy import EU_TAXONOMY, EXTRA_CHANNELS, MaturityTier
from services.intelligence.model_validation import ALL_HAZARDS, ledger_design, ledger_hazard
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
ADMIN = ("admin@meridian.demo", "Demo!admin1")


def _get(api) -> dict:
    r = api.get("/v1/realized-exposure/model-validation", headers=_login(api, *ADMIN))
    assert r.status_code == 200, r.text
    return r.json()


def test_the_event_record_check_counts_each_event_once_in_customer_words(api):
    d = _get(api)
    storms = api.s.execute(text("SELECT count(DISTINCT storm_id) FROM storm_events")).scalar()
    quakes = api.s.execute(text("SELECT count(*) FROM seismic_events WHERE CAST(magnitude AS FLOAT) >= 5")).scalar()
    for p in d["perils"]:
        assert not {"note", "verdict", "label"} & set(p), "the screen gets codes and names, not sentences"
        assert p["message"]["code"] in messages.catalogue()
        assert not messages.INTERNAL.search(p["message"]["label"])
        if not p["available"]:
            continue
        assert p["n_events_observed"] == {"storm": storms, "seismic": quakes}[p["peril"]]
        for b in p["bands"]:
            # an event counts once per place, so no place holds more events than the record has
            assert all(0 <= x["observed_events"] <= p["n_events_observed"] for x in b["samples"])


def test_every_hazard_is_the_register_with_the_record_counts(api):
    cov = _get(api)["coverage"]
    register = [*EU_TAXONOMY, *EXTRA_CHANNELS]
    assert [(r["id"], r["tier"]) for r in cov["rows"]] == [(h.id, h.tier.value) for h in register]
    # the tier and family words are the Coverage page's own catalogue entries, not a second set
    assert all(r["tier_name"] == messages.label(f"coverage.tier.{r['tier']}") for r in cov["rows"])
    assert all(r["family_name"] == messages.name("coverage.family", "beyond" if r["beyond_eu"] else r["family"])
               for r in cov["rows"])
    assert cov["summary"]["validated"] == sum(1 for h in register if h.tier is MaturityTier.CALIBRATED)

    groups = api.s.execute(text("SELECT hazard_type, method, count(*), count(*) FILTER (WHERE passed_gate) "
                                "FROM validation_run GROUP BY 1, 2")).all()
    assert cov["summary"]["runs"] == sum(g[2] for g in groups)
    assert cov["summary"]["unmapped_runs"] == 0, "every test on the record belongs to a hazard and a design"
    expect: dict[tuple[str, str], list[int]] = {}
    for hz, method, runs, passed in groups:
        if hz in ALL_HAZARDS:
            continue
        k = (ledger_hazard(hz).id, ledger_design(hz, method))
        expect.setdefault(k, [0, 0])
        expect[k][0] += runs
        expect[k][1] += passed
    got = {(r["id"], dz): [c["runs"], c["passed"]] for r in cov["rows"] for dz, c in r["tests"].items()}
    assert got == expect


def test_a_crop_hazard_is_counted_on_its_own_harvest_tests(api):
    e = _get(api)["economic"]
    for h in e["by_hazard"]:
        mine = [f for f in e["fits"] if f["hazard_driver"] == h["hazard"]]
        assert h["fits"] == len(mine) and h["passed"] == sum(f["passed"] for f in mine)
    assert e["n_pass"] == sum(h["passed"] for h in e["by_hazard"])
    assert not {"note", "method"} & set(e)
    years = [f["n_years"] for f in e["fits"] if f["n_years"]]
    assert (e["years_min"], e["years_max"]) == (min(years), max(years))


def test_model_risk_reads_the_register_not_a_sentence(api):
    from services.governance.model_risk import _score_cards, _words
    from services.intelligence.model_validation import hazard_for_channel
    for c in _score_cards(api.s):
        feeds = c.pop("_feeds", [])
        _words(c, feeds, {})
        reg = hazard_for_channel(c["hazard"])
        # the register's standing, and its account of the hazard in customer words (the Coverage page's), never the
        # register's or the model registry's engineers' notes
        assert reg is not None and c["standing"] == reg.tier.value
        assert c["basis"]["code"] == f"coverage.hazard.{reg.id}" and not messages.INTERNAL.search(str(c["basis"]["detail"]))
        assert "limitations" not in c
