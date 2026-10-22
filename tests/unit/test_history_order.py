"""A history is read in the order it was written — by its insert sequence, never by a timestamp (E51, E52, E86, E109, E116,
E118): now() is the same for every row one transaction writes. Every query of a history table that orders it must order by
`seq`. A list that only shows when things happened keeps its timestamp, with the row's id to break a tie (E118)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ("regulatory_task_event", "regulatory_filing_event", "supervision_request_message", "reg_case_message",
           "model_status_event", "regspec_signoff", "regulatory_filing",
           "model_registry", "model_drift_observation", "kri_threshold_version", "asset_conflicts", "report_snapshots",
           "access_audit_log", "approval_requests", "regulatory_task_mention", "webhook_deliveries",
           "entity_structure_import_rows", "reported_figure", "client_intake_user", "loss_runs",
           "asset_building_matches", "validation_run", "risk_decision", "feed_refresh_log", "gl_balance", "loan_arrears",
           "model_risk_review")
# activity lists: ordered by when, the id breaks a tie so the order (and a SCIM page) is the same every time
TIE_BROKEN = {"webhook_endpoints": "endpoint_id", "refresh_token": "token_id", "invoice": "invoice_id",
              "esign_request": "request_id", "customer_contract": "contract_id", "assurance_share": "share_id",
              "client_intake": "intake_id", "client_intake_document": "document_id", "entity_structure_imports": "import_id",
              "users": "user_id", "scim_group": "group_id", "webauthn_credential": "credential_id",
              "intake_sftp_keys": "key_id", "reported_filing": "filing_id", "reg_alert": "alert_id"}
_SUBQUERY = re.compile(r"\(\s*SELECT(?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)")
CODE = ("services", "api", "tests", "ml", "core", "scripts")


def order_by(sql: str) -> str | None:
    """The ORDER BY clause of a query — read through its parentheses ((COALESCE(…) = 'true') DESC, created_at DESC),
    up to LIMIT / OFFSET / the end of the query or of the bracket it sits in (E216: the clause was cut at the first ')')."""
    m = re.search(r"ORDER BY\s+", sql)
    if not m:
        return None
    depth, out = 0, []
    for i, ch in enumerate(sql[m.end():]):
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and re.match(r"\s(?:LIMIT|OFFSET|FOR|FETCH)\b|;", sql[m.end() + i:]):
            break
        out.append(ch)
    return " ".join("".join(out).split())


def strings(src: str):
    """(line, text) for every string the code holds, as Python reads it (E315): adjacent literals joined — a query split
    over two literals hid its table from its ORDER BY — single-, double- or triple-quoted alike, and an f-string whole,
    its placeholders written {}."""
    tree = ast.parse(src)
    inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in inner:
            yield n.lineno, n.value
        elif isinstance(n, ast.JoinedStr):
            yield n.lineno, "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)


def queries():
    """(place, SQL with its scalar subqueries folded away) for every SQL string in the code (migrations aside)."""
    for p in [f for d in CODE for f in ROOT.joinpath(d).rglob("*.py")]:
        if p.name == Path(__file__).name or "migrations" in p.parts:
            continue
        for line, sql in strings(p.read_text()):
            if "ORDER BY" in sql:                              # a scalar subquery's table is not what the query orders
                yield f"{p.relative_to(ROOT)}:{line}", _SUBQUERY.sub("()", sql)


def _ordered_by_time():
    """(table, place, ORDER BY) for every query that orders a table by a timestamp (any *_at — E109)."""
    for where, sql in queries():
        order = order_by(sql)
        if not (order and re.search(r"_at\b", order)):
            continue
        for t in (*HISTORY, *TIE_BROKEN):
            if re.search(rf"\bFROM\s+{t}\b", sql):
                yield t, where, order


def latest_by_time(tables) -> list[tuple[str, str, str]]:
    """(table, place, ORDER BY) for every query that takes the latest row of one of these tables by a timestamp — a
    timestamp ordered descending with DISTINCT ON or LIMIT 1 — except a read of the current rows (valid_to IS NULL),
    where the table's own validity marks what is current."""
    out = []
    for where, sql in queries():
        order = order_by(sql)
        if not (order and re.search(r"_at\b[^,]*\bDESC\b", order) and re.search(r"DISTINCT ON|LIMIT\s+1\b", sql)):
            continue
        if re.search(r"valid_to\s+IS\s+NULL", sql, re.I):
            continue
        out += [(t, where, order) for t in tables if re.search(rf"\bFROM\s+{t}\b", sql)]
    return out


def test_history_tables_are_ordered_by_their_sequence():
    bad = [f"{where} ORDER BY {o}" for t, where, o in _ordered_by_time() if t in HISTORY and "seq" not in o]
    assert not bad, bad


def test_an_order_by_is_read_through_its_parentheses():
    sql = """SELECT DISTINCT ON (hazard_type) * FROM validation_run
             ORDER BY hazard_type, (COALESCE(metrics->>'applicable', 'true') = 'true') DESC, created_at DESC LIMIT 5"""
    assert order_by(sql) == "hazard_type, (COALESCE(metrics->>'applicable', 'true') = 'true') DESC, created_at DESC"
    assert order_by("SELECT * FROM (SELECT * FROM t ORDER BY a, b) x") == "a, b"


def test_activity_lists_break_a_timestamp_tie_by_id():
    bad = [f"{where} ORDER BY {o}" for t, where, o in _ordered_by_time()
           if t in TIE_BROKEN and not re.search(rf"\b{TIE_BROKEN[t]}\b", o)]
    assert not bad, bad


def test_the_scan_reads_a_query_as_python_joins_it():
    """E315: a query split over two literals ('SELECT … FROM t ' 'ORDER BY created_at DESC LIMIT 1') hid its table from its
    ORDER BY; single quotes and f-strings were not read at all."""
    src = ('q1 = ("SELECT a FROM feed_refresh_log " "WHERE k = 1 ORDER BY created_at DESC LIMIT 1")\n'
           "q2 = 'SELECT a FROM gl_balance ORDER BY uploaded_at DESC LIMIT 1'\n"
           'q3 = f"SELECT a FROM {t} WHERE x = {y} ORDER BY seq DESC"\n')
    got = dict(strings(src))
    assert got[1] == "SELECT a FROM feed_refresh_log WHERE k = 1 ORDER BY created_at DESC LIMIT 1"
    assert got[2].startswith("SELECT a FROM gl_balance") and got[3] == "SELECT a FROM {} WHERE x = {} ORDER BY seq DESC"
