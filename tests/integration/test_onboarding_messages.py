"""Onboarding speaks in the message catalogue's words (UI standard, product owner 2026-10-16).

The entity structure (one entity at a time, and the stage → review → confirm import), the column-mapping editor, drop
folders, their SFTP keys and the upload templates used to send screens sentences written where they arose — field keys
('ownership_pct must be between 0 and 100', "consolidation_method='full' at 40% ownership", "set source_note"), file
paths ('data/reference/money/parameters.json', 'docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md'), an exception's own text handed
to the screen (str(e)), a template's fixed-list values as codes ('joisted_masonry'). Each refusal is now a catalogue
code (data/reference/messages.en.json, prefix onboarding.) with its values: the label on the screen, the detail behind
its ⓘ. These tests hold that on the code, the reference data and the API — and the defects found on the way:
  - a CSV row's provenance word was stored as its consolidation basis, so the IFRS 10 check never refused a CSV row;
  - an ownership that is not a number answered "Something went wrong";
  - the mapping note printed a field's key and nothing after it for a currency conversion.
"""
from __future__ import annotations

import ast
import io
import re
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from core import messages
from core.errors import UserError
from tests.integration.conftest import login

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
FILES = ["services/governance/entities.py", "services/governance/entity_structure_import.py",
         "services/governance/entity_extraction.py", "api/routers/entity_structure.py", "api/routers/intake_batches.py",
         "services/intake/mapping.py", "services/intake/dropfolder.py", "services/intake/sftp_keys.py",
         "services/intake/inbox.py", "services/intake/storage.py", "services/ingest/templates.py",
         "services/ingest/filing_import.py", "services/governance/provided_data.py"]
CODE = re.compile(r"(?:onboarding|intake|error)\.[a-z_]+(?:\.[a-z_]+)*")
# the refusals of these files: each is raised with a catalogue code (its first argument, or its second beside a sentence)
CODED = {"EntityError": 0, "ImportError_": 0, "UserError": 0, "ReadError": 0, "MappingError": 1, "ChannelError": 1}


def _strings(path: Path):
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and CODE.fullmatch(n.value):
            yield n.value, n.lineno


def test_every_code_in_the_code_is_in_the_catalogue():
    known = set(messages.catalogue()) | set(messages.names())
    missing = [f"{f}:{line} {code}" for f in FILES for code, line in _strings(ROOT / f) if code not in known]
    assert missing == [], f"Add these to data/reference/messages.en.json: {missing}"


def test_every_refusal_carries_a_catalogue_code():
    """No refusal of these files reaches a screen as a sentence: each names its catalogue code."""
    bad = []
    for f in FILES:
        for n in ast.walk(ast.parse((ROOT / f).read_text(encoding="utf-8"))):
            if not (isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and isinstance(n.exc.func, ast.Name)):
                continue
            at = CODED.get(n.exc.func.id)
            if at is None:
                continue
            arg = n.exc.args[at] if len(n.exc.args) > at else None
            dynamic = arg is not None and not isinstance(arg, ast.Constant)     # e.code passed on, checked where it is made
            if not dynamic and not (isinstance(arg, ast.Constant) and arg.value in messages.catalogue()):
                bad.append(f"{f}:{n.lineno} {n.exc.func.id}")
    assert bad == [], f"refusals without a catalogue code: {bad}"


def test_no_route_hands_an_exception_text_to_the_screen():
    for f in ("api/routers/entity_structure.py", "api/routers/intake_batches.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert "str(e)" not in src and "str(ex)" not in src, f


def test_onboarding_messages_are_sound():
    ours = {k: v for k, v in messages.catalogue().items() if k.startswith("onboarding.")}
    assert ours and not [p for p in messages.check() if p.startswith("onboarding.")]


def test_every_fixed_list_value_of_a_template_has_a_customer_name():
    """The mapping editor shows our value for each of theirs: never a code such as 'joisted_masonry'."""
    from services.ingest import templates as T
    from services.ingest.fields import VOCABS
    for vocab, v in VOCABS.items():
        if v.dynamic:
            continue
        got = T.value_labels(vocab)
        if vocab in T.WORDS_ALREADY:
            assert got is None and all(not U_INTERNAL.search(x) for x in v.values)
        else:
            assert set(got) == set(v.values) and not [w for w in got.values() if U_INTERNAL.search(w)], vocab
    fields = [f for name in dir(T) if name.endswith("_TEMPLATE_FIELDS") for f in getattr(T, name)]
    assert all(f.get("value_labels") is not None or f.get("vocab") in T.WORDS_ALREADY for f in fields if "allowed" in f)


U_INTERNAL = messages.INTERNAL


# ── entities, one at a time ──

def test_an_entity_refusal_is_the_catalogues_with_its_values():
    from services.governance import entities as E
    from services.governance.entities import EntityError
    e = E.basis_needed(40, "full")
    assert isinstance(e, UserError) and e.status == 409
    body = e.body()["error"]
    assert body["error"] == "onboarding.entity.basis_needed" and body["message"] == "Say why this consolidation method applies"
    assert "full consolidation at 40% ownership" in body["detail"]["what"] and "IFRS 10" in body["detail"]["why"]
    assert EntityError("onboarding.entity.not_found", 404).status == 404


# ── the entity-structure import, through the API ──

def _csv(rows: list[str], header="entity_name,parent_entity_name,kind,country,ownership_pct,consolidation_method,consolidation_basis"):
    return ("\n".join([header, *rows]) + "\n").encode()


def _stage(api, h, raw: bytes):
    return api.post("/v1/entity-structure/imports", headers=h, files={"file": ("structure.csv", io.BytesIO(raw), "text/csv")})


def test_a_csv_row_against_ownership_needs_its_basis(api):
    """Defect: the route stored 'customer-entered' as every CSV row's note, and the note is the row's consolidation
    basis — so full consolidation of a 40% stake confirmed with 'customer-entered' as its reason. The basis is now the
    CSV's own column: without it the row is refused; with it the entity carries the customer's reason."""
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    imp = _stage(api, h, _csv(["Onb Test Holding,,legal_entity,NL,100,full,", "Onb Test Minority,Onb Test Holding,legal_entity,NL,40,full,"]))
    assert imp.status_code == 201, imp.text
    assert all(r["source_note"] is None for r in imp.json()["rows"])
    r = api.post(f"/v1/entity-structure/imports/{imp.json()['import_id']}/confirm", headers=h)
    assert r.status_code == 409 and r.json()["error"]["error"] == "onboarding.structure.basis_needed"
    assert "Onb Test Minority is set to full consolidation at 40% ownership" in r.json()["error"]["detail"]["what"]

    why = "Majority of the board appointed under a shareholder agreement"
    imp = _stage(api, h, _csv(["Onb Test Holding 2,,legal_entity,NL,100,full,", f"Onb Test Minority 2,Onb Test Holding 2,legal_entity,NL,40,full,{why}"]))
    r = api.post(f"/v1/entity-structure/imports/{imp.json()['import_id']}/confirm", headers=h)
    assert r.status_code == 200, r.text
    basis = api.s.execute(text("SELECT consolidation_basis FROM reporting_entities WHERE name = 'Onb Test Minority 2'")).scalar()
    assert basis == why


def test_the_template_has_the_basis_column_and_its_example_confirms(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    raw = api.get("/v1/entity-structure/template.csv", headers=h).content
    assert raw.decode().splitlines()[0].endswith(",consolidation_basis")
    imp = _stage(api, h, raw.replace(b"Acme", b"Onb Tpl Acme"))
    assert imp.status_code == 201, imp.text
    assert api.post(f"/v1/entity-structure/imports/{imp.json()['import_id']}/confirm", headers=h).status_code == 200


def test_an_ownership_that_is_not_a_number_is_refused_naming_the_row(api):
    """Defect: float('40%') raised inside the route — the screen read 'Something went wrong'."""
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    r = _stage(api, h, _csv(["Onb Test Pct,,legal_entity,NL,40%,full,"]))
    assert r.status_code == 422 and r.json()["error"]["error"] == "onboarding.structure.ownership_number"
    assert "Onb Test Pct" in r.json()["error"]["detail"]["what"]


@pytest.mark.parametrize("raw, code", [(b"", "onboarding.structure.no_rows"),
                                      (_csv([",,legal_entity,NL,100,full,"]), "onboarding.structure.no_rows")])
def test_an_empty_structure_is_refused(api, raw, code):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    r = _stage(api, h, raw)
    assert r.status_code == 422 and r.json()["error"]["error"] == code


def test_a_row_the_entity_rules_refuse_names_the_row_and_the_reason(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    imp = _stage(api, h, _csv(["Onb Test Country,,legal_entity,XX,100,full,"]))
    r = api.post(f"/v1/entity-structure/imports/{imp.json()['import_id']}/confirm", headers=h)
    err = r.json()["error"]
    assert r.status_code == 409 and err["error"] == "onboarding.structure.row_refused"
    assert err["detail"]["what"] == "Onb Test Country: 'XX' is not a country code."


def test_a_confirmed_row_keeps_its_country(api):
    """Defect: the CSV's country was staged and shown for review, but confirm never passed it on — every entity an
    import created had no country (the organisation's was assumed for its records)."""
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    imp = _stage(api, h, _csv(["Onb Test Belgium,,legal_entity,BE,100,full,"]))
    assert api.post(f"/v1/entity-structure/imports/{imp.json()['import_id']}/confirm", headers=h).status_code == 200
    assert api.s.execute(text("SELECT country FROM reporting_entities WHERE name = 'Onb Test Belgium'")).scalar() == "BE"


def test_reading_a_structure_from_a_document_says_it_is_not_available(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.post("/v1/entity-structure/imports/extract", headers=h, files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")})
    assert r.status_code == 503 and r.json()["error"]["error"] == "onboarding.structure.extraction_unavailable"


def test_a_closed_import_says_so_in_words(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    imp = _stage(api, h, _csv(["Onb Test Closed,,legal_entity,NL,100,full,"])).json()
    assert api.post(f"/v1/entity-structure/imports/{imp['import_id']}/discard", headers=h).status_code == 200
    r = api.patch(f"/v1/entity-structure/imports/{imp['import_id']}/rows/{imp['rows'][0]['row_id']}", headers=h, json={"name": "x"})
    assert r.status_code == 409 and r.json()["error"]["detail"]["what"].startswith("The import is discarded.")


# ── mappings, drop folders, keys ──

def test_a_mapping_refusal_is_the_catalogues(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.post("/v1/intake/mappings", headers=h, json={"template": "bank_assets", "name": " ",
                                                          "column_map": {"asset_name": "Name"}})
    assert r.status_code == 400 and r.json()["error"]["error"] == "onboarding.mapping.name_required"
    r = api.post("/v1/intake/mappings", headers=h, json={"template": "bank_assets", "name": "Core",
                                                          "column_map": {"asset_name": "Name", "asset_type": "Name"}})
    assert r.status_code == 400 and r.json()["error"]["error"] == "onboarding.mapping.column_twice"
    r = api.post("/v1/intake/mappings", headers=h, json={"template": "bank_assets", "name": "Core",
                                                          "column_map": {"asset_name": "Name"}, "transforms": {"asset_name": {"multiply": 1000}}})
    err = r.json()["error"]
    assert err["error"] == "onboarding.mapping.not_money" and err["detail"]["what"].startswith("Asset name is not an amount")
    assert api.get("/v1/intake/templates/no_such/fields", headers=h).json()["error"]["error"] == "onboarding.template.unknown"


def test_a_drop_folder_refusal_is_the_catalogues(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    me = api.s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    r = api.post("/v1/intake/channels", headers=h, json={"template": "insurance_policies", "owner_user_id": me, "currency": "EUR"})
    err = r.json()["error"]
    assert r.status_code == 400 and err["error"] == "onboarding.dropfolder.other_sector" and "Statement of Values" in err["detail"]["what"]
    r = api.post("/v1/intake/channels", headers=h, json={"template": "bank_assets", "owner_user_id": me, "currency": "QQQ"})
    assert r.json()["error"]["error"] == "intake.refused.currency_unknown"


def test_a_key_refusal_is_the_catalogues(api):
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.post("/v1/intake/sftp-keys", headers=h, json={"label": "Core", "public_key": "AAAAC3NzaC1lZDI1NTE5AAAAIG"})
    assert r.status_code == 400 and r.json()["error"]["error"] == "onboarding.sftp.whole_line"
    r = api.post("/v1/intake/sftp-keys", headers=h, json={"label": "Core", "public_key": "ssh-dss AAAAB3NzaC1kc3MAAACBAP"})
    assert r.json()["error"]["error"] == "onboarding.sftp.type_refused" and "ssh-dss" in r.json()["error"]["detail"]["what"]
    assert api.delete("/v1/intake/sftp-keys/00000000-0000-4000-8000-000000000000", headers=h).json()["error"]["error"] == "onboarding.sftp.not_found"


def test_every_pick_up_outcome_is_named_with_its_message():
    from services.intake import dropfolder
    refusal = messages.render("intake.refused.missing_columns", n=1, columns="Asset name")
    for state in messages.names()["onboarding.sweep_state"]:
        got = dropfolder._said({"file": "f.csv", "state": state}, refusal if state == "refused" else None)
        assert got["state_label"] == messages.name("onboarding.sweep_state", state) and got["msg"]["label"]
        assert got["msg"] is refusal if state == "refused" else got["msg"]["code"].startswith("onboarding.dropfolder.")


def test_an_unavailable_drop_folder_or_store_says_so_in_words(monkeypatch):
    from core.config import settings
    from services.intake import inbox, storage
    monkeypatch.setattr(settings, "INTAKE_DROP_BACKEND", "s3")
    with pytest.raises(UserError) as e:
        inbox.backend()
    assert e.value.status == 503 and e.value.body()["error"]["message"] == "Drop folders are not set up"
    monkeypatch.setattr(settings, "INTAKE_STORAGE_BACKEND", "s3")
    with pytest.raises(UserError) as e:
        storage.put(b"x")
    assert e.value.status == 503 and e.value.code == "onboarding.storage.unavailable"


def test_the_mapping_note_names_each_converted_field():
    """Defect: a currency conversion printed '<field key>: ' and nothing after it — the report carried no rates; the
    note now reads each field's name and its currency (fixed, or a column's per row)."""
    from services.intake import mapping
    df = pd.DataFrame({"Name": ["A"], "Value": ["1"], "Ccy": ["USD"]})
    prof = {"profile_id": "p", "name": "Core", "version": 1, "column_map": {"asset_name": "Name", "appraised_value_eur": "Value"},
            "transforms": {"appraised_value_eur": {"multiply": 1000, "currency_column": "Ccy"}}}
    _, rep = mapping.apply(None, df, prof)
    assert [(c["label"], c["kind"]) for c in rep["conversions"]] == [("Appraised value", "scale"), ("Appraised value", "currency")]
    assert rep["conversions"][1]["currency_column"] == "Ccy"


def test_a_filed_report_the_reader_refuses_names_its_catalogue_code():
    from services.ingest import filing_import
    with pytest.raises(filing_import.ReadError) as e:
        filing_import.detect_format("report.docx", b"PK\x03\x04")
    assert e.value.code == "intake.prior.refused.unsupported_format" and e.value.code in messages.catalogue()


def test_a_provided_value_shows_its_status_and_source_in_words(session_rolled_back):
    from services.governance import provided_data as P
    s = session_rolled_back
    me = s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    org = s.execute(text("SELECT org_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    out = P.submit(s, org, me, framework="bank_p3esg", datapoint_key="p3_gar_aligned", value_num=12.5, value_text=None,
                   unit="%", source="vendor", provider_name="A vendor", data_vintage=None, period_label=None,
                   reporting_period_end="2025-12-31")
    row = next(r for r in P.provided_list(s, org, "bank_p3esg") if r["provided_id"] == out["provided_id"])
    assert (row["status_label"], row["source_label"]) == ("Waiting for a second person", "A data vendor")
