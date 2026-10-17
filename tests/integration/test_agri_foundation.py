"""How agriculture scores are produced (UI standard, 2026-10-16): the page reads its whole flow in one call — sources in
customer words with how current each is, the organisation's plots scored by band, and the euros split by what is
published — and the two cards under it give every reason as a catalogue message, never a sentence or a code. Rolled
back throughout."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core import messages
from services.intelligence.agri_foundation import BANDS, HAZARDS, SOURCES
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
ADMIN = ("admin@terra.demo", "Demo!admin1")
STATES = {"fresh", "due_soon", "overdue", "failed", "on_demand", "untracked"}


def _org(api) -> str:
    return api.s.execute(text("SELECT org_id::text FROM users WHERE email = :e"), {"e": ADMIN[0]}).scalar()


def test_the_flow_is_read_in_one_call_in_customer_words(api):
    h = _login(api, *ADMIN)
    r = api.get("/v1/supply/foundation", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()

    assert [s["code"] for s in d["sources"]] == [c for c, _ in SOURCES]
    for s in d["sources"]:
        assert s["state"] in STATES and s["feeds"] >= 1
        assert s["message"]["label"] and not messages.INTERNAL.search(s["message"]["label"])

    sc = d["scores"]
    plots = api.s.execute(text("SELECT COUNT(*) FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)"),
                          {"o": _org(api)}).scalar()
    assert sc["plots"] == plots and sc["cell_km2"] == pytest.approx(0.74, abs=0.01)
    for hz in sc["hazards"]:
        assert hz["hazard"] in HAZARDS and set(hz["bands"]) == set(BANDS)
        assert sum(hz["bands"].values()) == hz["plots"] <= sc["plots"]
    assert "baseline" not in sc["scenarios"] and "current" not in sc["years"]

    m = d["money"]
    assert m["published_crops"] + m["held_crops"] + m["pending_crops"] == m["crops"]
    assert m["published_spend_eur"] + m["held_spend_eur"] + m["pending_spend_eur"] == pytest.approx(m["spend_eur"], abs=3)


def test_the_cards_give_their_reasons_as_catalogue_messages(api):
    h = _login(api, *ADMIN)
    p = api.get("/v1/prices/pressure", headers=h).json()
    for c in p.get("commodities", []):
        if not c["covered"]:
            assert c["reason_message"]["code"].startswith("agri.data.price.") and "reason" not in c
    a = api.get("/v1/arrears/assessment", headers=h).json()
    if not a["available"]:
        assert a["message"]["code"] == "agri.data.arrears.none"
    for loan in a.get("loans", []):
        assert loan["reason_message"]["code"].startswith("agri.data.arrears.")
        assert "{" not in loan["reason_message"]["label"] and "rationale" not in loan


def test_an_unusable_upload_is_refused_in_customer_words(api):
    h = _login(api, *ADMIN)
    r = api.post("/v1/prices/rows", headers=h, json={"rows": [{"commodity": "cocoa", "period_ym": "2026-09", "index_value": "n/a"}]})
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["error"] == "agri.data.price.no_rows" and "row 1" in e["detail"]["what"]
    r = api.post("/v1/arrears/rows", headers=h, json={"rows": []})
    assert r.status_code == 422 and r.json()["error"]["error"] == "agri.data.file_empty"
