"""The supervisor's desk — requests and findings, service levels, the calendar by authority, the mandate registry, who is
regulated, deadlines, the entity file, evidence packs and onward shares — speaks customer words (UI standard, product
owner 2026-10-16): every explanation it sends is a catalogue message, every code it shows has its customer name beside
it, every refusal is a catalogue code, and the evidence pack names its two checks as the product does (Quick check, Full
rebuild) with its method in plain words. Through the HTTP API, in one rolled-back transaction: nothing is left behind.

Also: a deadline whose act no longer fixes a calendar date (the CSRD publication rule turns on a fact about each
undertaking; the ORSA runs from an event) still reads — it once failed the Deadlines tab and the calendar by authority."""
from __future__ import annotations

import io
import re
from datetime import date

import pdfplumber
import pytest
from sqlalchemy import text

from core import messages
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
SUPERVISOR = "88888888-8888-4888-8888-888888888888"      # EU Banking Supervisor (demo)
MERIDIAN = "11111111-1111-4111-8111-111111111111"        # a supervised bank with requests, filings and evidence packs
EXPLAINED = {"note", "reason", "message", "about", "rule"}   # keys that carry a server explanation to the screen
# not this desk's server explanations: what a person typed (a mandate setting's, an acknowledgement's and a pack's note),
# the registry's due-rule definition (a rule id and the act's wording, shown one click away), and each undertaking's CSRD
# scope reading (services/governance/csrd_scope, the CSRD pages' own words; this desk shows it inside a check's label)
SKIP = {"setting", "acknowledged", "packs", "due", "undertakings"}


def _is_message(m) -> bool:
    if not isinstance(m, dict) or m.get("code") not in messages.catalogue():
        return False
    return m["label"] == messages.render(m["code"], **(m.get("params") or {}))["label"] and bool(m["detail"].get("what"))


def _sentences(body, path="") -> list[str]:
    """Every plain string under an explanation key, anywhere in the response but SKIP."""
    out = []
    if isinstance(body, dict):
        for k, v in body.items():
            if k in SKIP or (k == "note" and re.search(r"\.deadlines\[\d+\]$", path)):    # a deadline's note: typed by the authority
                continue
            if k in EXPLAINED and isinstance(v, str):
                out.append(f"{path}.{k}: {v[:60]}")
            out += _sentences(v, f"{path}.{k}")
    elif isinstance(body, list):
        for i, v in enumerate(body):
            out += _sentences(v, f"{path}[{i}]")
    return out


def _refused(r, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert err["error"] == code and err["message"] and err["detail"]["what"], err


@pytest.fixture()
def sup(api):
    api.h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    return api


def test_the_desk_explains_in_catalogue_messages(sup):
    for path, key in (("/v1/supervisor/requests", "about"), ("/v1/supervisor/engagement/sla", "note"),
                      ("/v1/supervisor/obligations/calendar?period_label=FY2025", "note"), ("/v1/supervisor/mandates", "note"),
                      ("/v1/supervisor/population/mandates", None), ("/v1/supervisor/deadlines?period_label=FY2025", "note"),
                      (f"/v1/supervisor/entity/{MERIDIAN}/file", "about"), (f"/v1/supervisor/entity/{MERIDIAN}/evidence-packs", "about"),
                      ("/v1/supervisor/remittance/config", "about")):
        r = sup.get(path, headers=sup.h)
        assert r.status_code == 200, (path, r.text)
        body = r.json()
        assert not _sentences(body), (path, _sentences(body))
        assert key is None or _is_message(body[key]), (path, body.get(key))

    sla = sup.get("/v1/supervisor/engagement/sla", headers=sup.h).json()
    assert all(_is_message(m) for m in sla["definitions"].values())
    reqs = sup.get("/v1/supervisor/requests", headers=sup.h).json()
    automatic = messages.label("supervision.desk.request.automatic")
    for q in reqs["requests"]:
        assert (q["raised_by"] == automatic) == q["automatic"], q["raised_by"]
        assert (q["severity_label"] is not None) == (q["severity"] is not None)
        assert not q.get("source") or q["source"]["label"], q["source"]
    assert all(set(k["severity_labels"]) == set(k["severities"]) for k in reqs["kinds"].values())

    f = sup.get(f"/v1/supervisor/entity/{MERIDIAN}/file", headers=sup.h).json()
    assert f["entity"]["sector_label"] == "Credit institutions" and f["entity"]["country_name"] == "Spain"
    assert all(_is_message(m) for m in f["notes"])
    assert all(a["label"] and "." not in a["label"] for a in f["my_recent_accesses"]), f["my_recent_accesses"]
    assert all(r["kind_label"] for r in f["book"]["top_regions"]) and all(p["flag_label"] for p in f["peer_position"])
    assert all(fw["state_label"] for fw in (f["submissions"] or {}).get("frameworks", []))

    pop = sup.get("/v1/supervisor/population/mandates", headers=sup.h).json()
    assert all(e["sector_label"] and e["sector_label"] != e["type"] for e in pop["entities"])
    sector = [e["attributes"]["sector"] for e in pop["entities"] if "sector" in e["attributes"]]
    assert sector and all(a["value_label"] and a["source_label"] for a in sector)
    cal = sup.get("/v1/supervisor/obligations/calendar?period_label=FY2025", headers=sup.h).json()
    assert all(e["status_label"] and e["frequency_label"] and "sub" not in e for e in cal["events"])


def test_a_deadline_whose_act_sets_no_date_still_reads(sup):
    from services.supervision.mandates import due_date, mandate
    assert due_date(mandate("csrd_esrs_e1"), date(2030, 12, 31)) is None   # the premise: the rule turns on each undertaking
    sup.s.execute(text("""INSERT INTO supervision_deadline (regulator_org_id, mandate_id, framework, period_label, period_end, due_date, due_source)
                          VALUES (CAST(:r AS uuid), 'csrd_esrs_e1', 'esrs_pack', 'FY2030', '2030-12-31', '2031-04-30', 'registry')"""), {"r": SUPERVISOR})
    dl = sup.get("/v1/supervisor/deadlines?period_label=FY2030", headers=sup.h)
    assert dl.status_code == 200, dl.text
    row = next(d for d in dl.json()["deadlines"] if d["mandate_id"] == "csrd_esrs_e1")
    assert row["registry_due"] is None and row["registry_message"]["code"] == "supervision.desk.deadlines.no_calendar_rule"
    assert row["due_source_label"] == messages.names()["due_source"]["registry_changed"]      # not 'the act's rule'
    cal = sup.get("/v1/supervisor/obligations/calendar?period_label=FY2030", headers=sup.h)
    assert cal.status_code == 200, cal.text
    assert any(e["mandate_id"] == "csrd_esrs_e1" and e["date"] == "2031-04-30" for e in cal.json()["events"])
    _refused(sup.put(f"/v1/supervisor/deadlines/{row['deadline_id']}", headers=sup.h, json={"due_date": None}), 422,
             "supervision.desk.deadlines.no_calendar_rule")
    _refused(sup.put(f"/v1/supervisor/deadlines/{row['deadline_id']}", headers=sup.h, json={"due_date": "30/04/2031"}), 422,
             "supervision.desk.deadlines.bad_date")


def test_the_desk_refuses_in_catalogue_codes(sup):
    _refused(sup.get("/v1/supervisor/deadlines?period_label=2026-Q3", headers=sup.h), 422, "supervision.desk.period_invalid")
    _refused(sup.get("/v1/supervisor/entity/00000000-0000-4000-8000-000000000000/file", headers=sup.h), 404, "error.not_found")
    _refused(sup.post("/v1/supervisor/requests", headers=sup.h, json={"supervised_org_id": MERIDIAN, "kind": "finding", "title": "t"}), 422,
             "supervision.desk.request.needs_severity")
    _refused(sup.post("/v1/supervisor/requests", headers=sup.h, json={"supervised_org_id": MERIDIAN, "kind": "memo", "title": "t"}), 422,
             "supervision.desk.request.unknown_kind")
    rid = sup.get("/v1/supervisor/requests", headers=sup.h).json()["requests"][0]["request_id"]
    _refused(sup.post(f"/v1/supervisor/requests/{rid}/messages", headers=sup.h, json={}), 422, "supervision.desk.request.empty")
    _refused(sup.post("/v1/supervisor/population/mandates/ask", headers=sup.h, json={"supervised_org_id": MERIDIAN, "attributes": ["shoe_size"]}), 422,
             "supervision.desk.mandates.unknown_attributes")
    packs = sup.get(f"/v1/supervisor/entity/{MERIDIAN}/evidence-packs", headers=sup.h).json()["packs"]
    if packs:
        _refused(sup.post(f"/v1/supervisor/entity/{MERIDIAN}/evidence-packs/{packs[0]['pack_id']}/remit", headers=sup.h,
                          json={"recipient_kind": "college", "recipient_name": " ", "purpose": "p", "recipient_email": "a@b.eu"}), 422, "supervision.desk.remit.no_name")


def test_the_evidence_pack_names_its_checks_and_method_in_plain_words(sup):
    """The pack once titled its sections 'Tier 1 — plausibility…' / 'Tier 2 — independent lens' and printed its method
    with internal words (heat_acute, H3); the screens call the checks Quick check and Full rebuild."""
    p = sup.post(f"/v1/supervisor/entity/{MERIDIAN}/evidence-packs", headers=sup.h, json={})
    assert p.status_code == 201, p.text
    assert p.json()["label"] == messages.label("supervision.desk.pack.version", n=p.json()["version"])
    pdf = sup.get(f"/v1/supervisor/entity/{MERIDIAN}/evidence-packs/{p.json()['pack_id']}.pdf", headers=sup.h).content
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        words = " ".join(page.extract_text() or "" for page in doc.pages)
    sections = messages.names()["case_file_section"]
    assert f"3. {sections['plausibility']}" in words and f"4. {sections['lens']}" in words
    # the pack's own words: all but section 7, whose threads hold what the supervisor and the entity wrote
    own = words.split(f"7. {sections['engagement']}")[0] + words.split(f"8. {sections['access_trail']}")[-1]
    for said in ("Tier 1", "Tier 2", "heat_acute", "H3", "Shadow book", "independent lens", "supervisor.file.access"):
        assert said not in own, said
    content = sup.get(f"/v1/supervisor/entity/{MERIDIAN}/evidence-packs/{p.json()['pack_id']}.json", headers=sup.h).json()
    assert all(_is_message(m) for m in content["method"]["messages"])
    for key in ("plausibility", "lens"):
        assert content[key]["available"] or _is_message(content[key]["reason"]), content[key]
    assert re.search(r"\b(?:ES|DE|FR)\b · [A-Z]\b", own) is None, "a cell printed as its codes"
