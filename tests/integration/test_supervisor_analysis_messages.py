"""The supervisor's three analysis pages — the full rebuild (independent lens), the quick check (plausibility band) and
the population analytics — send their explanations as catalogue messages, never as sentences written where they arise
(UI standard, product owner 2026-10-16): every reason, rule, basis note and caption is a code from
data/reference/messages.en.json with its label and detail, and every template cell carries customer names beside its
codes. Through the HTTP API, in one rolled-back transaction: nothing is left behind.

Also: the template a page reads, when no year is asked for, is the latest financial year on file — never the latest
upload (a backfilled earlier year once became 'the template on file').
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core import messages
from tests.integration.conftest import login as _login
from tests.integration.money_method import state_method

pytestmark = pytest.mark.integration
SUPERVISOR = "88888888-8888-4888-8888-888888888888"      # EU Banking Supervisor (demo)
MERIDIAN = "11111111-1111-4111-8111-111111111111"        # a supervised bank with templates and granular data on file
EXPLAINED = {"note", "rule", "reason", "basis_note", "message"}    # keys that carry an explanation to the screen


def _is_message(m) -> bool:
    if not isinstance(m, dict) or m.get("code") not in messages.catalogue():
        return False
    r = messages.render(m["code"], **(m.get("params") or {}))
    return m["label"] == r["label"] and bool(m["detail"].get("what"))


def _sentences(body, path="") -> list[str]:
    """Every plain string under an explanation key, anywhere in the response."""
    out = []
    if isinstance(body, dict):
        for k, v in body.items():
            if k in EXPLAINED and isinstance(v, str):
                out.append(f"{path}.{k}: {v[:60]}")
            out += _sentences(v, f"{path}.{k}")
    elif isinstance(body, list):
        for i, v in enumerate(body):
            out += _sentences(v, f"{path}[{i}]")
    return out


def _named(cell: dict) -> bool:
    return bool(cell["geography_label"]) and bool(cell["sector_label"]) and cell["sector_label"] != cell["sector"]


def _period_end(s, org_id):
    from services.governance.filings import reporting_period_end
    return reporting_period_end(s, org_id)


def test_the_three_analysis_pages_explain_in_catalogue_messages(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    state_method(api.s, SUPERVISOR, _period_end(api.s, SUPERVISOR), {("method.at_risk_level", None): 50.0})

    lens = api.get(f"/v1/supervisor/entity/{MERIDIAN}/lens", headers=h).json()
    if lens["status"] == "no_submission":
        pytest.skip("no submitted template for the demo bank")
    assert lens["entity_name"] and not _sentences(lens), _sentences(lens)
    for c in lens["cells"]:
        assert _named(c), c
        assert (c["reason"] is None) if c["flag"] == "ok" else _is_message(c["reason"]), c
    for m in (lens.get("message"), lens["at_risk_level"]["message"], lens["bank_basis"]["message"]):
        assert m is None or _is_message(m), m
    first = lens["cells"][0]
    cell = api.get(f"/v1/supervisor/entity/{MERIDIAN}/lens/cell", headers=h,
                   params={"geography": first["geography"], "sector": first["sector"]}).json()
    assert _named(cell["cell"]) and _is_message(cell["rebuilt"]["rule"]) and not _sentences(cell)

    pl = api.get(f"/v1/supervisor/entity/{MERIDIAN}/plausibility", headers=h).json()
    assert pl["entity_name"] and not _sentences(pl), _sentences(pl)
    if pl.get("status") in ("gap", "no_submission"):
        assert _is_message(pl["message"])
    else:
        assert _is_message(pl["basis_note"]) and _is_message(pl["rule"])
        assert all(_named(r) and _is_message(r["reason"]) for r in pl["rows"])
        assert {r["verdict_label"] for r in pl["rows"]} <= {"Within range", "Above range", "Below range", "Not judged"}

    trend = api.get(f"/v1/supervisor/entity/{MERIDIAN}/trend", headers=h).json()
    assert _is_message(trend["note"]) and all(_named(c) for c in trend["cells"]) and not _sentences(trend)
    for path in ("/v1/supervisor/trend", "/v1/supervisor/timeliness"):
        body = api.get(path, headers=h).json()
        assert _is_message(body["note"]) and not _sentences(body), path
    an = api.get("/v1/supervisor/analytics", headers=h).json()
    assert _is_message(an["scenario_shift"]["note"]) and not _sentences(an), _sentences(an)
    assert all(a["message"] is None or _is_message(a["message"]) for a in an["anchor_coverage"]["anchors"])


def test_the_template_on_file_is_the_latest_year_not_the_latest_upload(api):
    from services.supervision.intake import load_submission
    s = api.s
    years = [r[0] for r in s.execute(text("""SELECT DISTINCT period_label FROM supervisor_submissions
        WHERE regulator_org_id = CAST(:r AS uuid) AND subject_org_id = CAST(:s AS uuid) AND framework = 'pillar3_esg'"""),
        {"r": SUPERVISOR, "s": MERIDIAN})]
    if not years:
        pytest.skip("no submitted template for the demo bank")
    # an earlier year arrives last — a backfill, or a correction to an old year
    s.execute(text("""INSERT INTO supervisor_submissions (regulator_org_id, subject_org_id, framework, template, period_label, basis, cells, n_cells)
                      VALUES (CAST(:r AS uuid), CAST(:s AS uuid), 'pillar3_esg', 'template_5', 'FY2019', '{}'::jsonb, '{}'::jsonb, 0)"""),
              {"r": SUPERVISOR, "s": MERIDIAN})
    assert load_submission(s, SUPERVISOR, MERIDIAN, "pillar3_esg", "template_5")["period_label"] == max(years)
    assert load_submission(s, SUPERVISOR, MERIDIAN, "pillar3_esg", "template_5", "FY2019")["period_label"] == "FY2019"
