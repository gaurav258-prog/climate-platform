"""The catastrophe-capital page speaks customer words (UI standard, 2026-10-16): what the standard formula still needs,
how a region was charged, the reinsurance, the incurred losses and every refusal arrive as catalogue messages (a label
for the screen, a structured detail for its pop-up) — never a sentence written where it arose, an internal key or an
exception's own text. End to end through the real API, rolled back."""
from __future__ import annotations

import pytest

from core.messages import INTERNAL, catalogue
from tests.integration.conftest import login

ALPENRUECK = ("admin@alpenrueck.demo", "Demo!admin1")     # insurer demo: standard formula incomplete, no stated method
IBERIA = ("admin@iberia.demo", "Demo!admin1")             # insurer demo: stated method, attested treaty, incurred losses
Q = "?scenario=baseline&horizon=current"


def _as(api, who):
    api.h = login(api, *who)
    return api


def _message(m: dict, prefix: str = "solvency.") -> None:
    assert m["code"].startswith(prefix) and m["code"] in catalogue(), m
    assert m["label"] and not INTERNAL.search(m["label"]) and m["detail"]["what"]


def test_what_the_standard_formula_still_needs_is_one_message_per_input(api):
    sf = _as(api, ALPENRUECK).get(f"/v1/insurance/solvency-scr{Q}", headers=api.h).json()["standard_formula_natcat"]
    assert sf["available"] and not sf["complete"] and sf["missing"]
    for m in sf["missing"]:
        _message(m)
        assert m["uncharged_eur"] >= 0
    assert len({(m["code"], tuple(sorted(m["params"].items()))) for m in sf["missing"]}) == len(sf["missing"])   # each once
    assert len(sf["incomplete"]) == len(sf["missing"])                   # the filing's lines are the same messages
    for p in sf["perils"].values():
        if p.get("other_regions"):
            _message(p["other_regions"]["message"])
        for r in p.get("regions", []):
            _message(r["method_message"], "solvency.method.")


def test_the_one_in_200_gross_and_net_add_up_and_match_the_capital_figure(api):
    _as(api, IBERIA)
    rein = api.get(f"/v1/insurance/reinsurance/attested{Q}", headers=api.h).json()
    scr = api.get(f"/v1/insurance/solvency-scr{Q}", headers=api.h).json()
    w = rein["one_in_200"]
    assert w["gross_eur"] - w["reinsurance_eur"] == w["net_eur"]
    assert w["gross_eur"] == round(scr["modelled_1_in_200_loss_eur"])    # one simulation: the card's gross is the waterfall's
    assert w["net_eur"] == round(rein["net"]["net_aep_eur"]["rp_200"])


def test_no_attested_treaty_is_a_message():
    from api.routers.insurance import _reinsurance_from_cat
    r = _reinsurance_from_cat({}, None, "baseline", "current")
    assert not r["available"] and r["message"]["code"] == "solvency.reinsurance.not_attested"


def test_incurred_losses_explain_themselves_in_messages(api):
    none = _as(api, ALPENRUECK).get(f"/v1/insurance/incurred-losses{Q}", headers=api.h).json()
    if none["status"] == "not_yet_supplied":
        assert "note" not in none
        _message(none["message"])
    got = _as(api, IBERIA).get(f"/v1/insurance/incurred-losses{Q}", headers=api.h).json()
    assert got["status"] == "supplied" and not {"comparison_note", "region_coverage_note", "modelled_coverage_note"} & set(got)
    _message(got["comparison"])
    for k in ("region_coverage", "modelled_coverage"):
        if got[k] is not None:
            _message(got[k])


@pytest.mark.parametrize("change,code", [
    ({"peril": "volcano"}, "solvency.incurred.error.peril"),
    ({"period_start": "2025-12-31", "period_end": "2025-01-01"}, "solvency.incurred.error.period_order"),
    ({"period_end": "2999-12-31"}, "solvency.incurred.error.period_open"),
    ({"net_incurred_loss_eur": 2_000_000}, "solvency.incurred.error.net_above_gross"),
    ({"currency": "XXX"}, "solvency.incurred.error.not_converted"),
])
def test_an_incurred_loss_is_refused_in_customer_words(api, change, code):
    body = {"period_start": "2025-01-01", "period_end": "2025-12-31", "peril": "flood",
            "gross_incurred_loss_eur": 1_000_000, "currency": "EUR", **change}
    r = _as(api, IBERIA).post("/v1/insurance/incurred-losses", headers=api.h, json=body)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["error"] == code and err["message"] and err["detail"]["what"]
    assert "XXX" not in err["message"] and "_eur" not in str(err)       # the cause goes to the log, not the screen
