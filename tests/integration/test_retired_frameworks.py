"""The three TCFD-style report types are retired (E87): reit_tcfd, assetmgmt_tcfd, insurer_climate.

  (a) none is offered, and preparing, refreshing or restating one, or providing a value for it, is refused with the
      reason of its retirement declaration (services.governance.filings.retirement_refusal);
  (b) a filing of each made before the retirement stays readable: register, form with its official annex, the json
      and xlsx exports, lineage entry points, retention and the assurance pack;
  (c) the KRI pages of the REIT, insurer and asset manager load on their new anchors, each KRI saying where it is filed
      or that it is live only.

The historical filings are created inside the rolled-back transaction (a snapshot frozen from the sector's live book,
inserted directly with its hash, and a filing over it), so nothing here reads a filing the demo data may or may not
hold (E81/E85)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from services.governance import filings as F
from services.governance import provided_data as P
from services.governance.report_snapshots import _sha256
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration

INSURER, REIT, AM = ("22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333",
                     "44444444-4444-4444-8444-444444444444")
RETIRED = {"reit_tcfd": (REIT, "reit", "admin@stellar.demo", "api.routers.realestate"),
           "insurer_climate": (INSURER, "insurer", "admin@iberia.demo", "api.routers.insurance"),
           "assetmgmt_tcfd": (AM, "asset_manager", "admin@nordkap.demo", "api.routers.assetmgmt")}
NEW_ANCHOR = {"reit": "reit_taxonomy", "insurer": "insurer_solvency", "asset_manager": "sfdr_pai"}


def _uid(s, email):
    return s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": email}).scalar()


def _historical(s, framework: str, status: str, year: int) -> str:
    """A filing of a retired framework as it was frozen before the retirement: the sector's book, hashed."""
    import importlib
    org, _, email, engine = RETIRED[framework]
    payload = importlib.import_module(engine).build_disclosure_snapshot(s, org, "baseline", "current")
    payload["_fx"] = {"presentation_currency": "EUR", "note": "This report is built from the euro book and presents in EUR."}
    version = (s.execute(text("SELECT COALESCE(max(version), 0) FROM report_snapshots WHERE org_id = CAST(:o AS uuid) "
                              "AND report_type = :t"), {"o": org, "t": framework}).scalar() or 0) + 1
    snap = s.execute(text("""
        INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, note, created_by, payload_sha256)
        VALUES (CAST(:o AS uuid), :t, :v, CAST(:b AS jsonb), CAST(:p AS jsonb), 'frozen before the retirement',
                CAST(:u AS uuid), :h) RETURNING snapshot_id::text"""),
                     {"o": org, "t": framework, "v": version, "u": _uid(s, email), "h": _sha256(json.loads(json.dumps(payload, default=str))),
                      "b": json.dumps({"scenario": "baseline", "horizon": "current", "reporting_period_end": f"{year}-12-31"}),
                      "p": json.dumps(payload, default=str)}).scalar()
    return s.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by,
                                       submission_ref)
        VALUES (CAST(:o AS uuid), :t, :pe, :pl, :st, CAST(:snap AS uuid), CAST(:u AS uuid), :ref)
        RETURNING filing_id::text"""), {"o": org, "t": framework, "pe": f"{year}-12-31", "pl": f"FY{year}", "st": status,
                                         "snap": snap, "u": _uid(s, email),
                                         "ref": "NCA-2024-0001" if status == "submitted" else None}).scalar()


@pytest.mark.parametrize("framework", sorted(RETIRED))
def test_a_retired_report_is_not_offered_and_nothing_new_is_made_for_it(api, framework, monkeypatch):
    s = api.s
    org, sector, email, _ = RETIRED[framework]
    why = F.retirement_refusal(framework)
    assert why and "retired since 2026-10-01" in why and "TCFD" in why
    assert framework not in {f["framework"] for f in F.available_frameworks(sector)}
    h = _login(api, email, "Demo!admin1")
    assert framework not in {f["framework"] for f in api.get("/v1/filings/frameworks", headers=h).json()["frameworks"]}
    # an unfiled obligation of it is owed no more (a demo row may exist from before: it is left out of the calendar)
    s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency)
                      VALUES (CAST(:o AS uuid), :f, '2095-12-31', 'FY2095', '2096-04-30', 'annual')"""),
              {"o": org, "f": framework})
    monkeypatch.setattr(F, "ensure_obligations", lambda *a: None)    # only the calendar read is under test here
    assert not [o for o in F.list_obligations(s, org, sector) if o["framework"] == framework and not o["filing_id"]]

    pre = api.get(f"/v1/filings/preflight?framework={framework}", headers=h)
    assert pre.status_code in (400, 409, 422) and "retired since 2026-10-01" in pre.text
    gen = api.post("/v1/filings", headers=h, json={"framework": framework, "confirm_token": "x"})
    assert gen.status_code in (400, 409, 422) and "retired since 2026-10-01" in gen.text

    draft, filed = _historical(s, framework, "draft", 2097), _historical(s, framework, "submitted", 2096)
    with pytest.raises(F.FilingError, match="retired since 2026-10-01"):
        F.refresh_filing(s, org, draft, _uid(s, email))
    with pytest.raises(F.FilingError, match="retired since 2026-10-01"):
        F.restate_filing(s, org, filed, _uid(s, email), "a correction after the retirement")
    with pytest.raises(P.ProvidedError, match="retired since 2026-10-01"):
        P.submit(s, org, _uid(s, email), framework=framework, datapoint_key="taxonomy_aligned", value_num=1.0,
                 reporting_period_end="2025-12-31")
    with pytest.raises(ValueError, match="retired since 2026-10-01"):
        from services.governance.report_snapshots import create_snapshot
        create_snapshot(s, org, framework, _uid(s, email), period_end="2025-12-31")


@pytest.mark.parametrize("framework", sorted(RETIRED))
def test_a_historical_filing_of_a_retired_report_stays_readable(api, framework):
    s = api.s
    org, _, email, _ = RETIRED[framework]
    h = _login(api, email, "Demo!admin1")
    fid = _historical(s, framework, "submitted", 2096)
    assert any(f["filing_id"] == fid for f in api.get("/v1/filings", headers=h).json()["filings"])
    one = api.get(f"/v1/filings/{fid}", headers=h)
    assert one.status_code == 200 and one.json()["snapshot"]["hash_verified"]
    form = api.get(f"/v1/filings/{fid}/form", headers=h)
    assert form.status_code == 200, form.text
    assert form.json()["groups"] and form.json()["annex"] and form.json()["annex"]["sections"]
    exp = api.get(f"/v1/filings/{fid}/export?format=json", headers=h)
    assert exp.status_code == 200 and json.loads(exp.content)["payload"]
    assert api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=h).status_code == 200
    assert api.get(f"/v1/filings/{fid}/lineage/hazards", headers=h).status_code == 200
    assert api.get(f"/v1/filings/{fid}/retention", headers=h).status_code == 200
    assert api.get(f"/v1/filings/{fid}/assurance-pack", headers=h).status_code == 200


@pytest.mark.parametrize("sector", sorted(NEW_ANCHOR))
def test_the_kri_pages_load_on_their_new_anchors(api, sector):
    org, email = {"reit": (REIT, "admin@stellar.demo"), "insurer": (INSURER, "admin@iberia.demo"),
                  "asset_manager": (AM, "admin@nordkap.demo")}[sector]
    h = _login(api, email, "Demo!admin1")
    fws = [f["framework"] for f in api.get("/v1/reg-tasks/kri/frameworks", headers=h).json()["frameworks"]]
    assert NEW_ANCHOR[sector] in fws and not set(fws) & set(RETIRED)
    d = api.get(f"/v1/reg-tasks/kri?framework={NEW_ANCHOR[sector]}", headers=h).json()
    assert d["supported"] and d["framework"] == NEW_ANCHOR[sector] and d["kpis"]
    tagged = [k for k in d["kpis"] if "live_only" in k]
    assert tagged and all(k["filed_basis"] for k in tagged)
    # a live-only KRI has no filed trend, whatever history the anchor report holds
    live = next(k for k in tagged if k["live_only"])
    det = api.get(f"/v1/reg-tasks/kri/detail?framework={NEW_ANCHOR[sector]}&kri={live['key']}", headers=h)
    assert det.status_code == 200 and det.json()["supported"] and det.json()["trend"]["points"] == []
    for fw in RETIRED:
        assert api.get(f"/v1/reg-tasks/kri?framework={fw}", headers=h).json()["supported"] is False


def test_an_open_breach_of_a_kri_set_the_org_no_longer_has_is_ended(session_rolled_back):
    """The REIT's set moved from reit_tcfd to reit_taxonomy: a breach episode still open under the old key is not left
    open for ever — the org-wide sweep ends it (services.governance.kri_monitor.observe)."""
    from services.governance import kri_monitor
    s = session_rolled_back
    eid = s.execute(text("""INSERT INTO kri_breach_episode (episode_id, org_id, framework, kri_key, label, severity, direction,
                                                            onset_value, peak_value, threshold)
                            VALUES (gen_random_uuid(), CAST(:o AS uuid), 'reit_tcfd', 'test_retired_set', 'A KRI of the old set', 'red',
                                    'higher_worse', 40, 40, 30) RETURNING episode_id::text"""), {"o": REIT}).scalar()
    kri_monitor.observe(s, REIT, None)
    assert s.execute(text("SELECT cleared_at IS NOT NULL FROM kri_breach_episode WHERE episode_id = CAST(:e AS uuid)"),
                     {"e": eid}).scalar()
