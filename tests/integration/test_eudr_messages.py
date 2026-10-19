"""The EUDR journey speaks in the message catalogue's words (UI standard, product owner 2026-10-16).

Every check of a statement, a simplified declaration and an Article 5 record, every refusal, the product's place on the
list of covered products, a reading that is not assessable, the window to amend or withdraw and each event used to be a
sentence written where it arose — with internal values ('not_negligible', 'micro_small_primary_operator'), article
citations and exception texts passed straight to the screen. Each is now a catalogue code (data/reference/messages.en.json,
prefix eudr.) with its values, and every code the records carry has its customer name (names.eudr.*). The platform gives
readings and checks, never a conclusion on compliance: the undertaking concludes (E108). These tests hold that on the code
and on every EUDR record in the database.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from core import messages
from scripts import ui_language as U
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TERRA = "55555555-5555-4555-8555-555555555555"
FILES = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "services" / "eudr").glob("*.py")) + ["api/routers/eudr.py"]
# the calls whose first argument is a catalogue code: the EUDR errors (each a core.errors.UserError) and the renderers
CODED = {"EudrError", "EudrFilingError", "DeclarationFilingError", "TradeError", "RecordError", "StatementError",
         "DeclarationError", "UserError", "render", "label", "finding", "_f"}
FAMILIES = {"scope", "completeness", "plausibility"}            # the filings checklist's families (filing/words CHECK_FAMILY)
VERDICT = re.compile(r"\b(?:non-?)?compliant\b|deforestation[- ]free|\bverdict\b|\billegal\b", re.I)
SAMPLE = dict(on="2027-01-15", start="2026-12-30", by="2024-12-31", basis="No entry covers it.", stated="Our reasons.",
              plot="Farm A", n=4, loss_ha="1.5", year=2022, reason="The plot is a point.", countries="CI (Standard risk)",
              since="2026-01-01", concern="Substantiated concern", size="Large", country="CI", risk="Standard risk",
              system="A national system", hs="180100", printed="1801", commodity="Cocoa", description="Cocoa beans",
              exception="bamboo", note="a note", decimals=6, ha=4, home="GH", checks="One check; another", state="a draft",
              latest="09 Jan 2027, 10:00 UTC", kept="26GHKGF0000017", missing="(a), (b)", name="Grouped",
              until="09 Jan 2027, 10:00 UTC", closes="09 Jan 2027, 10:00 UTC", path="Full assessment",
              conclusion="Not negligible")


def _coded_calls(path: Path):
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in CODED and re.fullmatch(r"[a-z]+(\.[a-z_]+)+", n.args[0].value):
                yield n.args[0].value, n.lineno


def _db_values(s, table: str, constraint: str) -> set[str]:
    """The values a database check constraint allows — the codes a record can carry."""
    d = s.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                       "AND conname = :c"), {"t": table, "c": constraint}).scalar()
    assert d, f"{table}.{constraint} is not in the database"
    return set(re.findall(r"'([a-z_]+)'::text", d))


@pytest.fixture()
def s():
    from core.db.session import get_session
    with get_session() as session:
        yield session
        session.rollback()


def test_every_code_the_eudr_journey_raises_or_renders_is_in_the_catalogue(s):
    """Static codes in the EUDR files, and every code they compose: a role that files no statement, a party's missing
    detail, each way the list of covered products decides, each reason a reading is not assessable, each event, each
    state of the window."""
    from services.eudr.checks import FILERS
    from services.eudr.words import _REASON_START
    known = set(messages.catalogue())
    static = [f"{f}:{line} {code}" for f in FILES for code, line in _coded_calls(ROOT / f) if code not in known]
    events = _db_values(s, "eudr_dds_event", "ck_eudr_event_kind")
    composed = (
        [f"eudr.check.filer.{r}" for r in _db_values(s, "eudr_movement", "ck_eudr_role") - set(FILERS)]
        + [f"eudr.check.{who}.{part}" for who in ("supplier", "customer") for part in ("missing", "name", "address", "email")]
        + [f"eudr.scope.{k}" for k in ("listed", "not_listed", "narrower_only", "ambiguous", "excepts_part", "ex_heading")]
        + [f"eudr.reading.not_assessable.{k}" for k in {k for _, k in _REASON_START} | {"point_no_radius", "unknown"}]
        + [f"eudr.event.{k}" for k in events | {"identifier_received"}]
        + [f"eudr.window.{k}" for k in ("open", "no_reference", "grouped", "placed_or_exported", "given_to_customs",
                                         "rejected", "check_notified", "expired")])
    assert static == [] and [c for c in composed if c not in known] == [], \
        f"Add these codes to data/reference/messages.en.json: {static + [c for c in composed if c not in known]}"


def test_every_eudr_message_renders_in_customer_words():
    """Each eudr.* code fills with its values (no {placeholder} left), passes the catalogue's own checks (label of one to
    eight words, a 'what'), says nothing internal and states no conclusion on compliance."""
    assert [p for p in messages.check() if p.startswith("eudr.")] == []
    bad = []
    for code in (c for c in messages.catalogue() if c.startswith("eudr.")):
        r = messages.render(code, **SAMPLE)
        for part in [r["label"], *r["detail"].values()]:
            if "{" in part or U.INTERNAL.search(part) or VERDICT.search(part):
                bad.append(f"{code}: {part[:80]}")
    assert bad == []


def test_every_code_an_eudr_record_carries_has_a_name(s):
    """The codes the database allows each have their customer name (names.eudr.*), so no screen prints a code — and no
    name states a verdict."""
    from api.routers.eudr import BOOKS
    names = messages.names()
    need = {
        "eudr.kind": _db_values(s, "eudr_movement", "ck_eudr_kind"),
        "eudr.actor": _db_values(s, "eudr_movement", "ck_eudr_role") | _db_values(s, "eudr_movement", "ck_eudr_supplier_role"),
        "eudr.outcome": _db_values(s, "eudr_plot_assessment", "ck_eudr_outcome") | {"unread"},
        "eudr.event": _db_values(s, "eudr_dds_event", "ck_eudr_event_kind") | {"identifier_received"},
        "eudr.aspect": _db_values(s, "eudr_legality_evidence", "ck_eudr_aspect"),
        "eudr.size": _db_values(s, "eudr_undertaking_statement", "ck_eudr_size"),
        "eudr.path": _db_values(s, "eudr_risk_assessment", "ck_eudr_path"),
        "eudr.conclusion": _db_values(s, "eudr_risk_assessment", "ck_eudr_conclusion")
                           | _db_values(s, "eudr_concern_step", "ck_eudr_step_conclusion"),
        "eudr.concern": _db_values(s, "eudr_concern", "ck_eudr_concern_kind"),
        "eudr.step": _db_values(s, "eudr_concern_step", "ck_eudr_step_kind"),
        "eudr.source": _db_values(s, "eudr_dds_reference", "ck_eudr_ref_source")
                       | _db_values(s, "eudr_declaration_identifier", "ck_eudr_decl_source"),
        "eudr.commodity": {e["commodity"] for v in json.loads((ROOT / "data/reference/eudr/annex_i.json").read_text())["versions"]
                           for e in v["entries"]},
        "eudr.country_risk": {"low", "standard", "high", "unclassified"},
        "eudr.book": set(BOOKS),
    }
    missing = {k: sorted(v - set(names.get(k, {}))) for k, v in need.items() if v - set(names.get(k, {}))}
    assert missing == {}
    worded = [f"{k}.{c}: {w}" for k, block in names.items() if k.startswith("eudr.") for c, w in block.items()
              if U.INTERNAL.search(w) or VERDICT.search(w)]
    assert worded == []


def test_a_refused_step_answers_with_a_catalogue_message(api):
    """A refusal reaches the screen as {error: {error: code, message: label, detail}} — never an exception's own text —
    and a product code of the wrong length is refused, not a server error (E-row C: it raised an unhandled ValueError)."""
    maker = _login(api, "analyst@terra.demo", "Demo!analyst1")
    for r, code, status in (
        (api.post("/v1/eudr/declaration/lines", headers=maker, json={"hs_code": "18010", "description": "Cocoa beans",
                                                                     "customs_flow": True, "est_net_mass_kg": 1000}),
         "eudr.refused.line.code", 422),
        (api.get("/v1/eudr/movements/00000000-0000-4000-8000-000000000000/statement", headers=maker),
         "eudr.refused.not_found.shipment", 404),
        (api.get("/v1/eudr/intake/eudr_ledger/template.xlsx", headers=maker), "eudr.refused.not_found.book", 404),
        (api.post("/v1/eudr/filings/00000000-0000-4000-8000-000000000000/withdraw", headers=maker,
                  json={"reason": "not on file at all"}), "eudr.refused.not_found.statement", 404),
    ):
        body = r.json()["error"]
        assert (r.status_code, body["error"]) == (status, code), r.text
        assert "{" not in body["message"]
        assert body["detail"]["what"] and not U.INTERNAL.search(body["message"] + body["detail"]["what"])


def test_every_check_on_file_speaks_the_catalogue(s):
    """Every check of every shipment's statement or record, and of every micro or small undertaking's declaration, on
    every organisation in the database, is a catalogue message in a checklist family, with nothing internal and no
    verdict; every current reading is explained by a known reason."""
    from services.eudr import declaration as D
    from services.eudr import trade as T
    from services.eudr.checks import checks
    from services.eudr.reading import current
    from services.eudr.statement import compute
    from services.eudr.words import reading_msg
    found = []
    for org, mv, role in s.execute(text("SELECT org_id::text, movement_id::text, actor_role FROM eudr_movement")).all():
        found += checks(compute(s, org, mv)) if role == "operator" else T.checks(T.compute(s, org, mv))
    for org, ent in s.execute(text("""SELECT DISTINCT org_id::text, reporting_entity_id::text FROM eudr_undertaking_statement
                                       WHERE size_class IN ('micro', 'small')""")).all():
        found += D.checks(D.compute(s, org, ent))
    assert found, "no EUDR record in the database to check"
    bad = [f"{f['rule']}: {f.get('msg')}" for f in found
           if not (f.get("msg") or {}).get("label") or f["category"] not in FAMILIES
           or any(U.INTERNAL.search(p) or VERDICT.search(p) for p in [f["msg"]["label"], *f["msg"]["detail"].values()])]
    assert bad == []
    plots = [r[0] for r in s.execute(text("SELECT DISTINCT plot_id::text FROM eudr_plot_assessment")).all()]
    unexplained = [p for p, r in current(s, plots).items() if r and reading_msg(r)["code"].endswith(".unknown")]
    assert unexplained == []


def test_request_titles_and_the_signature_line_are_customer_words(api):
    """What a second person sees in Approvals (the request's title) and the statement's printed signature line carry
    customer words: no internal value ('not_negligible'), no machine timestamp."""
    from services.eudr import records as REC
    from services.eudr.statement import sign_point_6
    s = api.s
    m = s.execute(text("SELECT movement_id::text FROM eudr_movement WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": TERRA}).scalar()
    user = s.execute(text("SELECT user_id::text FROM users WHERE email = 'analyst@terra.demo'")).scalar()
    from datetime import date
    REC.request_status(s, TERRA, user, entity_id=None, effective_from=date(2027, 1, 1), size_class="medium", country="ES",
                       address="Calle Mayor 1, Madrid")
    REC.request_assessment(s, TERRA, user, movement_id=m, path="full", conclusion="not_negligible",
                           criteria={k: "assessed" for k in REC.CRITERIA})
    titles = [t for (t,) in s.execute(text("""SELECT title FROM approval_requests WHERE org_id = CAST(:o AS uuid)
                                               AND request_type IN ('eudr.status', 'eudr.risk') ORDER BY seq DESC LIMIT 2"""),
                                      {"o": TERRA}).all()]
    assert len(titles) == 2 and not any(U.INTERNAL.search(t) for t in titles), titles
    annex = {"sections": [{"key": "eudr_annex_ii", "rows": [{"cells": [{"text": "6. Signature"}, {"text": ""}]}]}]}
    sign_point_6(annex, {"statement": {"annex_ii": {"1": {"name": "Terra Foods"}}}},
                 {"at": "2026-10-02T09:34:03.915749+02:00", "attestor_name": "Pia", "function": "Director", "email": "pia@x"})
    lines = [r["cells"][1]["text"] for r in annex["sections"][0]["rows"]]
    assert not any(re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", t) for t in lines), lines
