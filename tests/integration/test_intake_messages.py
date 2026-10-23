"""Data intake and lineage speak in the message catalogue's words (UI standard, product owner 2026-10-16).

The upload checks, the gate's reasons, a refused file, the exchange rates on a batch, a difference between the client's
value and ours, the trace from a filed figure to its source, the calculation run behind a filing, its retention, how it
moved against the prior one, the data dictionary and prior filings used to send screens sentences written where they
arose — column keys ('appraised_value_eur does not tie'), API paths and E-numbers ('GET /v1/filings/{id}/lineage/t5
(E105)'), method keys ('method.at_risk_level'), 'golden model'. Each is now a catalogue code (data/reference/messages.en.json,
prefix intake.) with its values: the label on the screen, the detail behind its ⓘ. The gate's sentences stay as they were
beside their messages — a second person's approval compares them word for word (services/intake/pipeline.decide).
These tests hold that, on the code, on the reference data and on the demo database.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from core import messages
from core.db.session import get_session
from scripts import ui_language as U
from tests.integration.test_intake_pipeline import BANK_ORG, DECL, _csv, _rows

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
FILES = ["services/ingest/batch_controls.py", "services/intake/pipeline.py", "services/intake/security.py",
         "services/intake/money.py", "services/intake/values.py", "services/intake/staging.py", "services/intake/mapping.py",
         "services/intake/catalog.py", "services/intake/conflicts.py", "services/intake/observations.py",
         "services/intake/inspect.py", "api/services/intake_http.py", "api/routers/intake_facts.py",
         "services/governance/filing_lineage.py", "services/governance/pillar3_lineage.py",
         "services/governance/record_retention.py", "services/governance/data_revisions.py",
         "services/governance/filing_variance.py", "services/governance/engine_runs.py",
         "services/governance/data_dictionary.py", "services/governance/prior_filings.py", "api/routers/prior_filings.py",
         "services/intake/workbooks.py", "services/intake/after_landing.py", "api/routers/intake_workbook.py"]
CODE = re.compile(r"intake\.[a-z_]+(?:\.[a-z_]+)+")
SAMPLE = dict(accepted="1,000.00", actual=4, age=12, book="loan tape", book_date="2026-06-30", columns="asset name", content="plain text",
              country="Japan", currencies="USD", currency="USD", date="2026-06-30", declared=5, difference="1.00", differences=2,
              dropped=1, end="2026-06-30", ending=".txt", examples="“Steel” (2)", field="Appraised value", fields="Occupancy",
              figures="Total book value", format="Legacy Excel", formats="CSV or XLSX", hazard="Flooding", law="An act, Art. 1",
              limit=5, mapped=30, mapping="Core banking", mb="12", n=3, note="It sets no period.", now=50, official="1.08",
              official_source="the ECB", ours="Germany", pct=6.5, pct_value=2.5, prior=70, raw="2,000.00", rejected="1,000.00",
              report="ESRS statement", rows="4, 7", scored=10, sector="Bank", since="2026-01-01", source="the ECB", start="2025-07-01",
              state="imported", successor="ESRS statement", symbols="$", units="1.08", validated=4, written="Frnace",
              years=10, yours="France")


def _literals(path: Path):
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and CODE.fullmatch(n.value):
            yield n.value, n.lineno


def test_every_intake_code_in_the_code_is_in_the_catalogue():
    """Every intake.* string these files use is a catalogue message or a names block (names.intake.book, …)."""
    known = set(messages.catalogue()) | set(messages.names())
    missing = [f"{f}:{line} {code}" for f in FILES for code, line in _literals(ROOT / f) if code not in known]
    assert missing == [], f"Add these to data/reference/messages.en.json: {missing}"


def test_every_code_built_from_a_key_is_in_the_catalogue():
    """The codes made from a key: each security finding (intake.security.<code>), each check of a calculation run
    (intake.run.<key>.pass / .warn), each projection method, each source category and lane of the data dictionary."""
    from services.governance.data_dictionary import LANES, SOURCE_CATEGORIES
    from services.governance.datapoint_catalog import CATALOG
    cat = set(messages.catalogue())
    sec = ROOT / "services/intake/security.py"
    findings = {n.args[0].value for n in ast.walk(ast.parse(sec.read_text())) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "_finding" and len(n.args) == 3}       # no case code of its own
    runs = ROOT / "services/governance/engine_runs.py"
    keys = {n.args[0].value for n in ast.walk(ast.parse(runs.read_text())) if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "_check" and n.args and isinstance(n.args[0], ast.Constant)} | {"input_tie"}
    warned = {"scored", "regulation", "specification", "differences", "feeds"}           # checks that pass with a point to note
    want = ({f"intake.security.{c}" for c in findings} | {f"intake.run.{k}.pass" for k in keys} | {f"intake.run.{k}.warn" for k in warned}
            | {"intake.prior.projection.compound", "intake.prior.projection.average"}
            | {f"intake.dictionary.source.{k}" for k in SOURCE_CATEGORIES} | {f"intake.dictionary.lane.{k}" for k in LANES})
    assert sorted(want - cat) == []
    used = {(d["source_category"], d["lane"]) for dps in CATALOG.values() for d in dps}
    assert {s for s, _ in used} <= set(SOURCE_CATEGORIES) and {lane for _, lane in used} <= set(LANES)


def test_every_intake_message_renders_in_customer_words():
    """Each intake.* code fills with its values (no {placeholder} left), has a label of at most eight words (the
    catalogue check) and says nothing internal — in its label or in any part of its detail."""
    assert [c for c in messages.check() if c.startswith("intake.")] == []
    bad = []
    for code in (c for c in messages.catalogue() if c.startswith("intake.")):
        r = messages.render(code, **SAMPLE)
        for part in [r["label"], *r["detail"].values()]:
            if "{" in part or U.INTERNAL.search(part):
                bad.append(f"{code}: {part[:80]}")
    assert bad == []


def test_every_name_these_screens_need_is_in_the_catalogue():
    """A book, a book's own column, a vertical, a retention document, a rate source, a feed's state and kind, a batch
    state, a fact's path — each key the data can hold has a customer name."""
    from services.data.feeds import FEEDS
    from services.governance import engine_runs as R
    from services.governance.record_retention import rules
    from services.ingest import sector_ingest as si
    from services.ingest.fields import FIELDS
    from services.reference.fx_sources import SOURCES
    n = messages.names()
    books = set(R._VERTICAL_BOOK.values()) | set(R._AGRI_BOOKS) | {"fund_positions", "other"}
    assert books - set(n["intake.book"]) == set()
    compare = {f for s in (getattr(si, a) for a in dir(si)) if hasattr(s, "compare") and hasattr(s, "name_field")
               for f in tuple(s.compare) + (("reporting_entity_id", "intragroup_entity_id") if s.group_entities else ())}
    assert {f for f in compare if f not in FIELDS and f.removesuffix("_id") not in FIELDS} - set(n["intake.book_field"]) == set()
    assert {d["document"] for d in rules()["documents"].values()} | {"unknown"} <= set(n["intake.retention_document"])
    assert {s.key for s in SOURCES} | {"identity", "client", "fallback"} <= set(n["intake.fx_source"])
    assert {f["maturity"] for f in FEEDS} <= set(n["intake.feed_maturity"])
    assert {"fresh", "due_soon", "overdue", "failed", "on_demand", "untracked"} <= set(n["intake.feed_state"])
    with get_session() as s:
        verticals = set(s.execute(text("SELECT DISTINCT vertical FROM portfolio_entities")).scalars())
        states = set(s.execute(text("SELECT DISTINCT state FROM ingest_batches")).scalars())
        paths = set(s.execute(text("SELECT DISTINCT method FROM asset_observations WHERE source = 'client'")).scalars())
    assert verticals - set(n["intake.vertical_book"]) == set()
    assert states | {"received", "checked", "held", "awaiting_approval", "imported", "rejected"} <= set(n["intake.batch_state"])
    assert paths | {"other"} <= set(n["intake.fact_path"])


def test_each_gate_reason_has_its_message():
    """The gate's sentences (compared word for word at approval) and the messages a screen shows stay one for one."""
    from services.ingest import batch_controls as bc
    df = pd.DataFrame(_rows("gate", n=3, bad=2)).astype(str)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)                       # a repeated row
    specs = [{"name": c, "label": c.replace("_", " ").capitalize(), "kind": "money" if c.endswith("_eur") else "text"} for c in df.columns]
    rep = {"n_total": len(df), "n_valid": 3, "n_error": 3, "errors": [{"row": i + 2} for i in (3, 4, 5)]}
    receipt = bc.receipt_check(df, declared={"row_count": 99}, labels={s["name"]: s["label"] for s in specs})
    tr = bc.transformation_check(df, specs, rep, [], value_field="appraised_value_eur")
    gate = bc.evaluate_gate(receipt, tr, 3)
    assert gate["status"] == "needs_signoff" and len(gate["messages"]) == len(gate["reasons"]) >= 3
    gate = bc.add_reason(gate, "Currency: 1 rate(s) need a second look — …", messages.render("intake.gate.currency", n=1))
    assert len(gate["messages"]) == len(gate["reasons"])
    for m in gate["messages"]:
        assert m["code"] in messages.catalogue() and not U.INTERNAL.search(m["label"]), m
    blocked = bc.evaluate_gate(receipt, tr, 0)
    assert blocked["status"] == "blocked" and [m["code"] for m in blocked["messages"]] == ["intake.gate.nothing_valid"]


def test_a_checked_file_shows_every_check_as_a_message(intake_client):
    """Through the real route (nothing is stored on a check): each receipt check, the left-out rows, the security
    inspection and the malware scan carry their message, the gate one message per reason, and none says anything
    internal."""
    rows = _rows("msgs", n=3, bad=1)
    raw = _csv(rows + [rows[0]])
    r = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker, files={"file": ("msgs.csv", raw)},
                           data={**DECL, "declared_row_count": "99"})
    assert r.status_code == 200, r.text
    rep = r.json()
    ctl = rep["controls"]
    shown = [c["msg"] for c in ctl["receipt"]["checks"]] + [ctl["transformation"]["excluded"]["msg"], rep["security"]["malware_msg"]]
    shown += ctl["gate"]["messages"]
    assert len(ctl["gate"]["messages"]) == len(ctl["gate"]["reasons"])
    assert {"intake.receipt.duplicates", "intake.receipt.row_count_differs"} <= {m["code"] for m in shown}
    for m in shown:
        assert m and m["code"] in messages.catalogue() and m["label"] and not U.INTERNAL.search(m["label"] + " ".join(m["detail"].values())), m
    assert ctl["transformation"]["excluded"]["value_label"] and "_" not in ctl["transformation"]["excluded"]["value_label"]


def test_a_refused_file_answers_with_its_catalogue_message(intake_client):
    """A refusal is {error: short key, code, message: the label, detail, msg} — never the exception's own text."""
    r = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker, files={"file": ("wrong.csv", b"foo,bar\n1,2\n")}, data=DECL)
    err = r.json()["error"]
    assert r.status_code == 400 and err["error"] == "missing_columns" and err["code"] == "intake.refused.missing_columns"
    assert err["message"] == err["msg"]["label"] and err["detail"]["what"] and "_" not in " ".join(err["missing_labels"])
    r = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker, files={"file": ("x.csv", _csv(_rows("decl")))},
                           data={**DECL, "declared_row_count": "four"})
    assert r.status_code == 400 and r.json()["error"]["error"] == "intake.refused.declared_rows", r.text


def test_a_rate_used_on_a_batch_says_which_and_why(session_rolled_back):
    from services.intake.money import rate_message
    base = {"currency": "USD", "book_date": "2026-06-30", "units_per_eur": 1.08, "source": "ecb", "rate_date": "2026-06-30",
            "policy": "closing", "basis": "reference_daily", "stale": False}
    cases = {"intake.rate.closing": base, "intake.rate.average": {**base, "policy": "average", "period_start": "2025-07-01", "period_end": "2026-06-30"},
             "intake.rate.stale": {**base, "stale": True, "rate_date": "2026-05-01", "age_days": 60},
             "intake.rate.later": {**base, "stale": True, "rate_date": "2026-07-03"},
             "intake.rate.peg": {**base, "source": "peg", "basis": "fixed_peg"}, "intake.rate.fallback": {**base, "source": "fallback", "stale": True},
             "intake.rate.own": {**base, "source": "client"},
             "intake.rate.own_differs": {**base, "source": "client", "official": {"units_per_eur": 1.07, "source": "ecb"}, "outside_tolerance": True, "difference_pct": 0.9}}
    for code, r in cases.items():
        m = rate_message(r)
        assert m["code"] == code and not U.INTERNAL.search(m["label"] + " ".join(m["detail"].values())), (code, m)


def test_lineage_says_why_a_report_has_no_hazard_trace_in_catalogue_words():
    from services.governance.filing_lineage import _ALT_LINEAGE, _NO_HAZARD_CELLS
    from services.governance.pillar3_lineage import _unsupported
    cat = set(messages.catalogue())
    assert set(_ALT_LINEAGE.values()) | set(_NO_HAZARD_CELLS.values()) <= cat
    assert _unsupported({"framework": "sfdr_pai"}, {}) in cat


def test_retention_gaps_are_messages(session_rolled_back):
    from services.governance.record_retention import retention_for
    s = session_rolled_back
    ids = s.execute(text("SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND snapshot_id IS NOT NULL LIMIT 5"),
                    {"o": BANK_ORG}).scalars().all()
    assert ids
    for fid in ids:
        r = retention_for(s, BANK_ORG, fid)
        assert r["document_label"] and all(g["code"] in messages.catalogue() for g in r["gaps"])
        assert all(x["runs_from_label"] for x in r["rules"])


def test_the_dictionary_reads_its_fields_and_users_from_data(session_rolled_back):
    """Every field is a scored hazard named by names.hazard; the reports that use it are the organisation's own live
    filings that froze it — not a typed list."""
    from core.types import HazardType
    from services.governance.data_dictionary import data_dictionary
    s = session_rolled_back
    d = data_dictionary(s, BANK_ORG)
    live = set(s.execute(text("SELECT DISTINCT framework FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) "
                              "AND status NOT IN ('superseded', 'withdrawn') AND snapshot_id IS NOT NULL"), {"o": BANK_ORG}).scalars())
    assert {f["field"] for f in d["fields"]} == {h.value for h in HazardType}
    assert all(f["label"] == messages.name("hazard", f["field"]) and {c["framework"] for c in f["consumed_by"]} <= live for f in d["fields"])
    assert all(c["label"] != "Another report" for f in d["fields"] for c in f["consumed_by"]) and all(fw["label"] != "Another report" for fw in d["frameworks"])
    assert all(x["state_label"] for f in d["fields"] for x in f["source_feeds"])


def test_a_calculation_runs_checks_read_as_messages(session_rolled_back):
    from services.governance.engine_runs import get_run
    s = session_rolled_back
    runs = s.execute(text("SELECT run_id::text FROM engine_runs WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC LIMIT 10"),
                     {"o": BANK_ORG}).scalars().all()
    assert runs
    for rid in runs:
        run = get_run(s, BANK_ORG, rid)
        assert all(b["label"] for b in run["inputs"]["books"])
        for c in run["checks"]:
            assert c["msg"]["code"] != "intake.run.other.pass" and c["msg"]["code"] in messages.catalogue(), c


def test_a_prior_filing_refusal_is_a_catalogue_error(intake_client):
    r = intake_client.post("/v1/prior-filings/upload", headers=intake_client.maker, files={"file": ("empty.xbrl", b"")},
                           data={"framework": "bank_p3esg", "period_label": "FY2096"})
    err = r.json()["error"]
    assert r.status_code == 400 and err["error"] == "intake.prior.refused.empty" and err["message"] and err["detail"]["what"]
