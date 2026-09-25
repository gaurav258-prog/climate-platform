"""Intake phase 2 end to end through the real HTTP routes: column mapping, engine-readiness, and matching a re-sent
book to the assets we already hold (update, never duplicate). Principles: the client's value wins on facts about their
own assets, a blank never clears a value, a big change needs a second person, and an approval imports exactly what
was checked.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from tests.integration.test_intake_pipeline import _csv, _landed, _purge, _rows

pytestmark = pytest.mark.integration


@pytest.fixture()
def tag():
    import uuid
    t = uuid.uuid4().hex[:8]
    yield t
    _purge(t)
    with get_session() as s:   # mapping profiles are immutable in production; only this cleanup lifts the trigger
        s.execute(text("UPDATE ingest_batches SET mapping_profile_id = NULL WHERE mapping_profile_id IN "
                       "(SELECT profile_id FROM intake_mapping_profiles WHERE name LIKE :n)"), {"n": f"%{t}%"})
        s.execute(text("ALTER TABLE intake_mapping_profiles DISABLE TRIGGER trg_mapping_profile_worm"))
        s.execute(text("DELETE FROM intake_mapping_profiles WHERE name LIKE :n"), {"n": f"%{t}%"})
        s.execute(text("ALTER TABLE intake_mapping_profiles ENABLE TRIGGER trg_mapping_profile_worm"))
        s.commit()


def _with_refs(tag, rows):
    return [{**r, "external_ref": f"{tag}-L{i}"} for i, r in enumerate(rows)]


def _up(c, tag, rows, name="f", **data):
    return c.post("/v1/bank/assets/upload", headers=c.maker, files={"file": (f"{tag}-{name}.csv", _csv(rows))}, data=data)


def _book(tag):
    with get_session() as s:
        return {r["external_ref"] or r["entity_name"]: dict(r) for r in s.execute(text("""
            SELECT e.entity_name, e.external_ref, CAST(e.primary_value_eur AS FLOAT) AS v, e.region,
                   CAST(x.outstanding_loan_balance_eur AS FLOAT) AS bal
            FROM portfolio_entities e LEFT JOIN ext_banking x ON x.entity_id = e.entity_id WHERE e.entity_name LIKE :p
        """), {"p": f"TEST-PIPE-{tag}%"}).mappings().all()}


def test_resent_book_updates_assets_instead_of_duplicating(intake_client, tag):
    rows = _with_refs(tag, _rows(tag, n=4))
    assert _up(intake_client, tag, rows, "v1").status_code == 200
    rows2 = [dict(r) for r in rows]
    rows2[0]["appraised_value_eur"] = 1_100_000                     # +10%: an ordinary update
    rows2.append({**rows[1], "asset_name": f"TEST-PIPE-{tag}-NEW", "external_ref": f"{tag}-L9"})
    r = _up(intake_client, tag, rows2, "v2")
    assert r.status_code == 200, r.text
    m = r.json()["controls"]["matching"]
    assert (m["new"], m["update"], m["unchanged"]) == (1, 1, 3)
    assert m["updates"][0]["changes"]["primary_value_eur"] == [1_000_000.0, 1_100_000.0]
    assert _landed(tag) == 5 and _book(tag)[f"{tag}-L0"]["v"] == 1_100_000.0
    led = intake_client.get(f"/v1/intake/batches/{r.json()['batch_id']}", headers=intake_client.maker).json()
    assert {s["match_status"] for s in led["staged"]} == {"new", "update", "unchanged"}


def test_name_and_location_match_attaches_the_customer_id(intake_client, tag):
    rows = _rows(tag, n=3)
    assert _up(intake_client, tag, rows, "noref").status_code == 200
    r = _up(intake_client, tag, _with_refs(tag, rows), "withref")
    assert r.status_code == 200, r.text
    assert r.json()["controls"]["matching"]["update"] == 3 and _landed(tag) == 3
    assert set(_book(tag)) == {f"{tag}-L0", f"{tag}-L1", f"{tag}-L2"}


def test_a_blank_value_never_clears_what_we_hold(intake_client, tag):
    rows = [{**r, "outstanding_loan_balance_eur": 750_000, "region": "IDF"} for r in _with_refs(tag, _rows(tag, n=2))]
    assert _up(intake_client, tag, rows, "full").status_code == 200
    blank = [{**r, "outstanding_loan_balance_eur": None, "region": None} for r in rows]
    r = _up(intake_client, tag, blank, "blank")
    assert r.status_code == 200, r.text
    assert r.json()["controls"]["matching"]["unchanged"] == 2
    b = _book(tag)[f"{tag}-L0"]
    assert b["bal"] == 750_000.0 and b["region"] == "IDF"


def test_rows_the_engine_cannot_use_are_rejected_with_a_reason(intake_client, tag):
    rows = _rows(tag, n=60) + [{**_rows(tag, n=1)[0], "asset_name": f"TEST-PIPE-{tag}-ZERO", "latitude": 0, "longitude": 0}]
    r = _up(intake_client, tag, rows)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["n_error"] == 1 and "0,0" in b["errors"][0]["problems"][0] and b["controls"]["readiness"]["n_not_ready"] == 1
    assert _landed(tag) == 60


def test_ambiguous_and_duplicate_rows_are_refused_not_guessed(intake_client, tag):
    base = _rows(tag, n=1)[0]
    twin = [base, {**base, "latitude": base["latitude"] + 0.0005}]      # two live assets, same name, 55 m apart
    assert _up(intake_client, tag, twin, "twins").status_code == 200
    others = [{**r, "external_ref": f"{tag}-X{i}"} for i, r in enumerate(_rows(tag + "o", n=30))]
    dup = {**others[0]}                                                   # same id twice in one file
    r = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker,
                    files={"file": (f"{tag}-amb.csv", _csv([base] + others + [dup]))})   # preview: shows why, lands nothing
    assert r.status_code == 200, r.text
    assert r.json()["controls"]["matching"]["ambiguous"] == 1
    probs = " | ".join(p for e in r.json()["errors"] for p in e["problems"])
    assert "share this name" in probs and "add your asset ID" in probs and "more than once" in probs


def test_large_change_needs_a_second_person_and_replay_refuses_if_the_book_moved(intake_client, tag):
    rows = _with_refs(tag, _rows(tag, n=3))
    assert _up(intake_client, tag, rows, "v1").status_code == 200
    big = [dict(r) for r in rows]
    big[0]["appraised_value_eur"] = 3_000_000                          # +200%
    r = _up(intake_client, tag, big, "big")
    assert r.status_code == 409 and any("change a lot" in x for x in r.json()["error"]["controls"]["gate"]["reasons"])
    r = _up(intake_client, tag, big, "big", approval_reason="Revaluation after refurbishment, confirmed by valuer.")
    assert r.status_code == 202, r.text
    rid = r.json()["approval_request_id"]
    assert _book(tag)[f"{tag}-L0"]["v"] == 1_000_000.0                  # nothing lands before approval

    with get_session() as s:                                            # the asset changes while awaiting approval
        s.execute(text("UPDATE portfolio_entities SET primary_value_eur = 2000000 WHERE external_ref = :r"), {"r": f"{tag}-L0"})
        s.commit()
    d = intake_client.post(f"/v1/approvals/{rid}/decide", headers=intake_client.checker, json={"decision": "approved", "reason": "ok checked"})
    assert d.status_code == 409 and "changed" in d.text

    with get_session() as s:
        s.execute(text("UPDATE portfolio_entities SET primary_value_eur = 1000000 WHERE external_ref = :r"), {"r": f"{tag}-L0"})
        s.commit()
    d = intake_client.post(f"/v1/approvals/{rid}/decide", headers=intake_client.checker, json={"decision": "approved", "reason": "ok checked"})
    assert d.status_code == 200, d.text
    assert _book(tag)[f"{tag}-L0"]["v"] == 3_000_000.0 and _landed(tag) == 3


def test_mapping_profile_renames_scales_and_converts(intake_client, tag):
    src = [{"Loan ID": f"{tag}-M{i}", "Borrower": f"TEST-PIPE-{tag}-M{i}", "Kind": "commercial_real_estate", "Lat": 48.85 + i / 100,
            "Lng": 2.35, "Value (k USD)": 1000, "Sector": "Commercial real estate", "EVIC": 100_000_000} for i in range(3)]
    raw = _csv(src)
    miss = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)})
    assert miss.status_code == 400
    sug = miss.json()["error"]["suggested_mapping"]
    assert sug["latitude"] == "Lat" and sug["longitude"] == "Lng" and sug["external_ref"] == "Loan ID"

    cmap = {**sug, "asset_name": "Borrower", "asset_type": "Kind", "appraised_value_eur": "Value (k USD)",
            "counterparty_evic_eur": "EVIC", "sector": "Sector"}
    p = intake_client.post("/v1/intake/mappings", headers=intake_client.maker,
                    json={"template": "bank_assets", "name": f"Core banking {tag}", "column_map": cmap,
                          "transforms": {"appraised_value_eur": {"multiply": 1000, "currency": "USD"}}})
    assert p.status_code == 201, p.text
    pid = p.json()["profile_id"]
    assert p.json()["version"] == 1

    pv = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)},
                     data={"mapping_profile_id": pid})
    assert pv.status_code == 200, pv.text
    conv = pv.json()["mapping"]["conversions"]
    rate = next(c for c in conv if c["kind"] == "currency")["rates"]["USD"]["rate"]
    stale = pv.json()["mapping"].get("warnings")
    data = {"mapping_profile_id": pid}
    if stale:   # the held FX rate is older than the book date: a person must accept it (never silently used)
        assert any(r.startswith("Mapping:") for r in pv.json()["controls"]["gate"]["reasons"])
        data["approval_reason"] = "Accepting the latest held USD rate for this test book."
    r = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)}, data=data)
    assert r.status_code in (200, 202), r.text
    if r.status_code == 202:
        d = intake_client.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=intake_client.checker,
                        json={"decision": "approved", "reason": "rate accepted"})
        assert d.status_code == 200, d.text
    assert _landed(tag) == 3
    assert _book(tag)[f"{tag}-M0"]["v"] == pytest.approx(round(1_000_000 * rate, 2))
    with get_session() as s:
        assert s.execute(text("SELECT mapping_profile_id::text FROM ingest_batches WHERE filename = :f AND state = 'imported'"),
                         {"f": f"{tag}.csv"}).scalar() == pid
