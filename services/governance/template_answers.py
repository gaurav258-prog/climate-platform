"""The answers to template items the platform cannot compute — one store for every document template
(template_answers): a fund's SFDR pre-contractual and periodic documents, an insurer's ORSA climate analysis and its
recovery-plan indicators, and any later one.

An answer targets one item of the governing specification's template, and only an item its binding says is answered
(never a computed or a fixed one). Its shape follows the item's kind:

  question           {"text": str} and / or {"percent": number} (a question asking for a rate or a share)
  field              {"text": str}
  choice             {"ticked": bool} (+ "percent": number where the box prints '___%', + "text" where it prints a blank)
  chart              {"values": {<chart_label item id>: number}} — the planned shares the answer commits to
  table              {"rows": [ {<table_column item id>: value, ...}, ... ]}

The subject is the organisation, or one of its funds; a periodic document's answers belong to one reference period.
Clearing an item is an answer of None. Refused answers are reported back, never dropped silently.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


class AnswerError(ValueError):
    pass


def shape(item: dict, children: list[dict], value) -> dict:
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


_KEY = """org_id = CAST(:o AS uuid) AND fund_id IS NOT DISTINCT FROM CAST(:f AS uuid)
          AND reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND family = :fam
          AND document = :d AND period_end IS NOT DISTINCT FROM CAST(:pe AS date)"""


def read(session: Session, org_id: str, family: str, document: str, *, fund_id: str | None = None,
         period_end: date | None = None, entity_id: str | None = None) -> dict:
    """{item id: answer} of one subject's document (for one reference period, where the document has one). The subject
    is a fund, a reporting entity, or (neither) the organisation as a whole."""
    return {r[0]: r[1] for r in session.execute(text(f"SELECT item_id, value FROM template_answers WHERE {_KEY}"),
                                                {"o": org_id, "f": fund_id, "e": entity_id, "fam": family, "d": document,
                                                 "pe": period_end})}


def save(session: Session, org_id: str, family: str, document: str, template: dict, bound: dict, answers: dict,
         user_id: str | None, *, fund_id: str | None = None, period_end: date | None = None,
         entity_id: str | None = None, label: str = "the template", computed_from: str = "the platform",
         validate=None) -> dict:
    """Validate every answer against the template and its binding ({item id: 'computed' | 'input'}), store the valid
    ones, report the refused ones. validate(item, value) → the stored answer, or None to use the kind's shape: a
    family whose answers carry more than the kind (ESRS: an omission and its reason) validates them itself."""
    by_id = {i["id"]: i for i in template["items"]}
    key = {"o": org_id, "f": fund_id, "e": entity_id, "fam": family, "d": document, "pe": period_end}
    saved, refused = [], []
    for item_id, value in (answers or {}).items():
        item = by_id.get(item_id)
        try:
            if item is None:
                raise AnswerError(f"{item_id}: {label} has no such item")
            if bound.get(item_id) != "input":
                raise AnswerError(f"{item_id}: {'computed from ' + computed_from if bound.get(item_id) else 'printed wording'}"
                                  " — not answered here")
            if value is None:
                session.execute(text(f"DELETE FROM template_answers WHERE {_KEY} AND item_id = :i"), {**key, "i": item_id})
                saved.append(item_id)
                continue
            stored = (validate(item, value) if validate else None) or \
                shape(item, [c for c in template["items"] if c.get("parent") == item_id], value)
        except AnswerError as e:
            refused.append({"item": item_id, "reason": str(e)})
            continue
        session.execute(text("""
            INSERT INTO template_answers (org_id, fund_id, reporting_entity_id, family, document, period_end, item_id, value,
                                         updated_by, updated_at)
            VALUES (CAST(:o AS uuid), CAST(:f AS uuid), CAST(:e AS uuid), :fam, :d, CAST(:pe AS date), :i, CAST(:v AS jsonb),
                    CAST(:u AS uuid), now())
            ON CONFLICT ON CONSTRAINT ux_template_answers DO UPDATE SET value = EXCLUDED.value,
                updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at"""),
            {**key, "i": item_id, "v": json.dumps(stored), "u": user_id})
        saved.append(item_id)
    return {"saved": saved, "refused": refused}
