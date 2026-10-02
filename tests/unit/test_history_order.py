"""A history is read in the order it was written — by its insert sequence, never by a timestamp (E51, E52, E86, E109, E116,
E118): now() is the same for every row one transaction writes. Every query of a history table that orders it must order by
`seq`. A list that only shows when things happened keeps its timestamp, with the row's id to break a tie (E118)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ("regulatory_task_event", "regulatory_filing_event", "supervision_request_message", "reg_case_message",
           "model_status_event", "regspec_signoff", "regulatory_filing",
           "model_registry", "model_drift_observation", "kri_threshold_version", "asset_conflicts", "report_snapshots",
           "access_audit_log", "approval_requests", "regulatory_task_mention", "webhook_deliveries",
           "entity_structure_import_rows", "reported_figure", "client_intake_user")
# activity lists: ordered by when, the id breaks a tie so the order (and a SCIM page) is the same every time
TIE_BROKEN = {"webhook_endpoints": "endpoint_id", "refresh_token": "token_id", "invoice": "invoice_id",
              "esign_request": "request_id", "customer_contract": "contract_id", "assurance_share": "share_id",
              "client_intake": "intake_id", "client_intake_document": "document_id", "entity_structure_imports": "import_id",
              "users": "user_id", "scim_group": "group_id", "webauthn_credential": "credential_id",
              "intake_sftp_keys": "key_id", "reported_filing": "filing_id"}
_STRING = re.compile(r'"""(.*?)"""|"((?:[^"\\\n]|\\.)*)"', re.S)


def _ordered_by_time():
    """(table, place, ORDER BY) for every query that orders a table by a timestamp (any *_at — E109)."""
    for p in [*ROOT.joinpath("services").rglob("*.py"), *ROOT.joinpath("api").rglob("*.py"), *ROOT.joinpath("tests").rglob("*.py")]:
        if p.name == Path(__file__).name:
            continue
        src = p.read_text()
        for m in _STRING.finditer(src):
            sql = m.group(1) or m.group(2) or ""
            sql = re.sub(r"\(\s*SELECT(?:[^()]|\([^()]*\))*\)", "()", sql)   # a scalar subquery's table is not what the query orders
            order = re.search(r"ORDER BY\s+([^\n)]*)", sql)
            if not (order and re.search(r"_at\b", order.group(1))):
                continue
            for t in (*HISTORY, *TIE_BROKEN):
                if re.search(rf"\bFROM\s+{t}\b", sql):
                    yield t, f"{p.relative_to(ROOT)}:{src[:m.start()].count(chr(10)) + 1}", order.group(1).strip()


def test_history_tables_are_ordered_by_their_sequence():
    bad = [f"{where} ORDER BY {o}" for t, where, o in _ordered_by_time() if t in HISTORY and "seq" not in o]
    assert not bad, bad


def test_activity_lists_break_a_timestamp_tie_by_id():
    bad = [f"{where} ORDER BY {o}" for t, where, o in _ordered_by_time()
           if t in TIE_BROKEN and not re.search(rf"\b{TIE_BROKEN[t]}\b", o)]
    assert not bad, bad
