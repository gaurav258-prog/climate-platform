"""The manager's answers to a fund's SFDR template items (fund_sfdr_answers), and the live (unfrozen) document.

An answer targets one item of the governing sfdr_product version's annex for the fund's classification, and only an
item the binding says the manager answers (never a computed or fixed one). Its shape follows the item's kind:

  question           {"text": str} and / or {"percent": number} (a question asking for a rate or a share)
  field              {"text": str}
  choice             {"ticked": bool} (+ "percent": number where the box prints '___%', + "text" where it prints a blank)
  chart              {"values": {<chart_label item id>: number}} — the planned shares the manager commits to
  table              {"rows": [ {<table_column item id>: value, ...}, ... ]}

A periodic answer belongs to one reference period; a pre-contractual one stands until changed. Clearing an item is an
answer of None. Refused answers are reported back, never dropped silently.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

import services.regspec as R
from services.governance import product_filings as P
from services.governance import sfdr_product as S

DOCUMENTS = {"precontractual": "sfdr_precontractual", "periodic": "sfdr_periodic"}


class AnswerError(ValueError):
    pass


def _context(session: Session, org_id: str, fund_id: str, document: str, on: date | None = None) -> tuple[dict, dict, dict, date | None]:
    if document not in DOCUMENTS:
        raise AnswerError("document is 'precontractual' or 'periodic'")
    fund = P.fund_of(session, org_id, fund_id)
    if fund is None:
        raise AnswerError("fund not found")
    try:
        P.check(session, org_id, DOCUMENTS[document], None, fund_id)
    except P.ProductScopeError as e:
        raise AnswerError(str(e)) from e
    from services.governance.filings import reporting_period_end
    period = reporting_period_end(session, org_id) if document == "periodic" else None
    spec = R.governing(S.FAMILY, period_end=period or date.today(), disclosure_date=on)
    if spec is None:
        raise AnswerError("no adopted SFDR template specification governs today")
    t = R.template(spec, P.annex(DOCUMENTS[document], fund["sfdr_classification"]))
    return fund, spec, t, period


def _shape(item: dict, children: list[dict], value) -> dict:
    """The answer as stored, or AnswerError naming what is wrong with it."""
    def num(v, what):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= float(v) <= 100:
            raise AnswerError(f"{item['id']}: {what} must be a percentage between 0 and 100")
        return float(v)
    if not isinstance(value, dict):
        raise AnswerError(f"{item['id']}: an answer is an object (see the item's kind)")
    k = item["kind"]
    if k in ("question", "field"):
        out = {}
        if isinstance(value.get("text"), str) and value["text"].strip():
            out["text"] = value["text"].strip()
        if k == "question" and value.get("percent") is not None:       # a question asking for a rate or a share
            out["percent"] = num(value["percent"], "the percentage")
        if not out:
            raise AnswerError(f"{item['id']}: the answer needs its text" + (" or a percentage" if k == "question" else ""))
        return out
    if k == "choice":
        if not isinstance(value.get("ticked"), bool):
            raise AnswerError(f"{item['id']}: say whether the box is ticked (true / false)")
        out = {"ticked": value["ticked"]}
        if item.get("blank") == "percent" and value.get("percent") is not None:
            out["percent"] = num(value["percent"], "the percentage")
        if item.get("blank") == "text" and value.get("text"):
            out["text"] = str(value["text"]).strip()
        return out
    if k == "chart":
        vals, ids = value.get("values"), {c["id"] for c in children}
        if not isinstance(vals, dict) or not vals or set(vals) - ids:
            raise AnswerError(f"{item['id']}: values are keyed by the chart's own labels ({', '.join(sorted(ids))[:200]})")
        return {"values": {cid: num(v, cid) for cid, v in vals.items()}}
    if k == "table":
        cols, rows = {c["id"] for c in children}, value.get("rows")
        if not isinstance(rows, list) or any(not isinstance(r, dict) or set(r) - cols for r in rows):
            raise AnswerError(f"{item['id']}: rows are keyed by the table's own columns")
        return {"rows": rows}
    raise AnswerError(f"{item['id']}: a {k} is not answered")


def save(session: Session, org_id: str, fund_id: str, document: str, answers: dict, user_id: str | None) -> dict:
    """Validate every answer against the governing template, store the valid ones, report the refused ones."""
    fund, spec, t, period = _context(session, org_id, fund_id, document)
    bound = S.binding(spec)[t["id"]]["items"]
    by_id = {i["id"]: i for i in t["items"]}
    saved, refused = [], []
    for item_id, value in (answers or {}).items():
        item = by_id.get(item_id)
        try:
            if item is None:
                raise AnswerError(f"{item_id}: {t['code']} of {spec['act']['short']} has no such item")
            if bound.get(item_id) != "input":
                raise AnswerError(f"{item_id}: {'computed from the fund' if bound.get(item_id) else 'printed wording'} — not answered by the manager")
            if value is None:
                session.execute(text("""DELETE FROM fund_sfdr_answers WHERE fund_id = CAST(:f AS uuid) AND document = :d
                                        AND period_end IS NOT DISTINCT FROM :pe AND item_id = :i"""),
                                {"f": fund_id, "d": document, "pe": period, "i": item_id})
                saved.append(item_id)
                continue
            stored = _shape(item, [c for c in t["items"] if c.get("parent") == item_id], value)
        except AnswerError as e:
            refused.append({"item": item_id, "reason": str(e)})
            continue
        session.execute(text("""
            INSERT INTO fund_sfdr_answers (fund_id, document, period_end, item_id, value, updated_by, updated_at)
            VALUES (CAST(:f AS uuid), :d, :pe, :i, CAST(:v AS jsonb), CAST(:u AS uuid), now())
            ON CONFLICT ON CONSTRAINT ux_fund_sfdr_answers DO UPDATE SET value = EXCLUDED.value,
                updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at"""),
            {"f": fund_id, "d": document, "pe": period, "i": item_id, "v": json.dumps(stored), "u": user_id})
        saved.append(item_id)
    return {"saved": saved, "refused": refused}


def live(session: Session, org_id: str, fund_id: str, document: str) -> dict:
    """The fund's document as it stands now (not frozen): every item of the governing template with its value."""
    from services.governance.sfdr_product_forms import missing
    fund, spec, t, period = _context(session, org_id, fund_id, document)
    book = S.freeze(session, org_id, fund_id, document, period or date.today())
    built = S.build(spec, t["id"], book)
    return {"fund": {"fund_id": fund_id, "name": fund["name"], "sfdr_classification": fund["sfdr_classification"]},
            "document": document, "report_type": DOCUMENTS[document], "template": t["id"], "title": t["title"],
            "citation": R.citation(spec, t["id"]), "spec_version": spec["version"], "period_end": period and period.isoformat(),
            "items": built, "missing": [m["id"] for m in missing(built)],
            "unmapped": {k: v for k, v in book["answers"].items() if k.startswith(("legacy.", "website."))},
            "interpretations": [i for i in spec.get("interpretations") or [] if i.get("resolves", {}).get("template") == t["id"]]}
