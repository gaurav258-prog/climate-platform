"""The ESRS statement (E1, E3, E4) of one undertaking or group for one financial year, item by item, built from the
governing specification version: the printed wording as is; each datapoint through its concept's lane (computed by the
platform — services.governance.esrs_statement; the undertaking's attested figure; a derived ratio); narratives and
choices as the undertaking answers them; and, for anything omitted, the undertaking's stated reason:

  not_material               the topic, or the datapoint, is assessed not material (2023 ESRS 1 §32, §34(b); 2026
                             ESRS 1 §24; for climate change a detailed explanation — 2023 ESRS 1 §32, 2026 ESRS 2 §37(b))
  condition_not_applicable   the item's printed condition does not apply ('if the undertaking …')
  phase_in                   a phase-in of data/reference/esrs/phase_ins.json the undertaking uses (checked in
                             services.governance.esrs_checks)

Answers are stored in template_answers (family 'esrs', document = the standard, per undertaking and period); the topic
materiality under document 'materiality'.
"""
from __future__ import annotations

from datetime import date

import services.regspec as R
from services.governance import esrs_binding as B
from services.governance import template_answers as TA

FAMILY = "esrs"
TOPICS = ("E1", "E3", "E4")
REASONS = ("not_material", "condition_not_applicable", "phase_in")
_MATERIALITY = {"id": "materiality", "items": [{"id": t, "kind": "question", "label": f"ESRS {t}"} for t in TOPICS]}


class DocumentError(ValueError):
    pass


def governing(session, org_id: str, period_end: date) -> dict:
    from services.calc_settings import get_calc_settings
    spec = R.governing(FAMILY, period_end=period_end, elections=get_calc_settings(session, org_id))
    if spec is None:
        raise DocumentError(f"no ESRS version governs the financial year ending {period_end}")
    return spec


def _validate(item: dict, value) -> dict | None:
    """An omission and its reason; anything else is the kind's own answer shape (template_answers.shape)."""
    if not isinstance(value, dict) or "omitted" not in value:
        if item["kind"] != "field":
            return None
        if isinstance(value, dict) and str(value.get("text") or "").strip():
            return {"text": str(value["text"]).strip()}       # the narrative part of a field that also asks to explain
        raise TA.AnswerError(f"{item['id']}: its figures are computed or stated as provided values (family 'esrs') — "
                             "here only its narrative or its omission and reason")
    om = value["omitted"]
    if not isinstance(om, dict) or om.get("reason") not in REASONS:
        raise TA.AnswerError(f"{item['id']}: an omission states its reason — one of {REASONS}")
    if om["reason"] == "condition_not_applicable" and not item.get("conditional"):
        raise TA.AnswerError(f"{item['id']}: the item has no printed condition — it cannot be 'not applicable'")
    if om["reason"] == "phase_in" and not om.get("phase_in"):
        raise TA.AnswerError(f"{item['id']}: name the phase-in used")
    if om["reason"] in ("not_material", "condition_not_applicable") and not str(om.get("statement") or "").strip():
        raise TA.AnswerError(f"{item['id']}: say why ({om['reason'].replace('_', ' ')})")
    return {"omitted": {k: om.get(k) for k in ("reason", "phase_in", "statement") if om.get(k) is not None}}


def _validate_topic(item: dict, value) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("material"), bool):
        raise TA.AnswerError(f"{item['id']}: state whether the topic is material (true / false)")
    expl = str(value.get("explanation") or "").strip()
    if item["id"] == "E1" and value["material"] is False and not expl:
        raise TA.AnswerError("E1: omitting climate change needs a detailed explanation of the materiality assessment "
                             "(2023 ESRS 1 §32; 2026 ESRS 2 §37(b))")
    return {"material": value["material"], **({"explanation": expl} if expl else {})}


def save(session, org_id: str, user_id: str, *, entity_id: str | None, period_end: date, standard: str,
         answers: dict) -> dict:
    spec = governing(session, org_id, period_end)
    if standard == "materiality":
        return TA.save(session, org_id, FAMILY, "materiality", _MATERIALITY, {t: "input" for t in TOPICS}, answers, user_id,
                       period_end=period_end, entity_id=entity_id, label="the materiality statement", validate=_validate_topic)
    t = next((x for x in spec["templates"] if x["id"] == standard), None)
    if t is None:
        raise DocumentError(f"ESRS {standard} is not in {spec['act']['short']}")
    bound = {i["id"]: "input" for i in R.items_to_fill(t)}
    return TA.save(session, org_id, FAMILY, standard, t, bound, answers, user_id, period_end=period_end,
                   entity_id=entity_id, label=f"ESRS {standard}", validate=_validate)


def answers(session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    return {d: TA.read(session, org_id, FAMILY, d, period_end=period_end, entity_id=entity_id)
            for d in (*TOPICS, "materiality")}


def build(spec: dict, statement: dict, provided: dict, ans: dict) -> list[dict]:
    """Every item of every standard in reading order, with its value(s), answer, omission and status."""
    concepts = statement.get("concepts") or {}
    material = ans.get("materiality") or {}
    sections = []
    for t in spec["templates"]:
        topic = material.get(t["id"])
        own = ans.get(t["id"]) or {}
        items = []
        for i in t["items"]:
            row = {k: i.get(k) for k in ("id", "kind", "label", "parent", "note", "obligation", "conditional", "narrative")}
            if i["kind"] in B.FIXED:
                row["status"] = "printed"
                items.append(row)
                continue
            a = own.get(i["id"])
            if topic is not None and topic.get("material") is False:
                row.update(status="omitted", omission={"reason": "not_material", "scope": "topic"})
            elif a and a.get("omitted"):
                row.update(status="omitted", omission=a["omitted"])
            elif i["kind"] in B.ANSWERED:
                row.update(status="filled" if a else "missing", answer=a)
            else:
                dps = [_datapoint(d, concepts, provided) for d in B.lane_of(spec, i)["datapoints"]]
                filled = all(d["status"] in ("filled", "derived", "computed") for d in dps)
                needs_text = bool(i.get("narrative")) and not (a and a.get("text"))
                row.update(datapoints=dps, answer=a,
                           status="filled" if filled and not needs_text else "missing")
            items.append(row)
        sections.append({"standard": t["id"], "title": t["title"], "topic": topic, "items": items})
    return sections


def _datapoint(d: dict, concepts: dict, provided: dict) -> dict:
    out = {"key": d["key"], "lane": d["lane"]}
    if d["lane"] == "same_as":
        parts = [provided.get(c) or concepts.get(c) for c in d["same_as"]]
        out.update(concept=d["same_as"], value=[p and (p.get("value")) for p in parts],
                   status="filled" if all(p and p.get("value") is not None for p in parts) else "missing")
        return out
    c = d["concept"]
    out["concept"] = c
    if d["lane"] in ("computed", "derived"):
        v = concepts.get(c) or {}
        out.update(value=v.get("value"), by_horizon=v.get("by_horizon"), unit=v.get("unit"),
                   status=("gap" if v.get("status") == "gap" or v.get("value") is None else v.get("status")),
                   gap=v.get("gap"))
        return out
    members = [p for k, p in provided.items() if k.startswith(c + "@")]
    p = provided.get(c)
    if members:
        out.update(value={p["member"]: p["value"] for p in members}, status="filled")
    elif p is not None:
        out.update(value=p["value"], currency=p.get("currency"), value_eur=p.get("value_eur"), status="filled")
    else:
        out.update(value=None, status="missing")
    return out


# ───────────────────────────── the filing: what is frozen ─────────────────────────────

def _provided(session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    from services.governance.provided_data import ESRS, attested_values
    return {v["concept"] + (f"@{v['member']}" if v.get("member") else ""): v
            for v in attested_values(session, org_id, ESRS, period_end, reporting_entity_id=entity_id)}


def _previous(session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    """The previous period's figures (ESRS 1 §83): the undertaking's attested values for it, and the platform's figures
    as frozen in the latest non-withdrawn statement filed for it (the same undertaking)."""
    from datetime import timedelta

    from sqlalchemy import text

    from services.regspec import fy_start
    prev_end = fy_start(period_end) - timedelta(days=1)
    out = {k: {"value": v["value"], "source": "attested"} for k, v in _provided(session, org_id, entity_id, prev_end).items()}
    row = session.execute(text("""
        SELECT rs.payload->'document_report'->'statement'->'concepts' AS c, rf.filing_id::text AS fid
        FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = CAST(:o AS uuid) AND rf.framework = 'esrs_pack' AND rf.period_end = :pe
          AND rf.entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND rf.status NOT IN ('withdrawn', 'superseded')
        ORDER BY rf.seq DESC LIMIT 1
    """), {"o": org_id, "pe": prev_end, "e": entity_id}).mappings().first()
    for k, c in ((row or {}).get("c") or {}).items():
        v = (c or {}).get("by_horizon") or (c or {}).get("value")        # a figure stated per time horizon, as stated
        if v is not None:
            out.setdefault(k, {"value": v, "source": f"filing {row['fid']}"})
    return {"period_end": prev_end.isoformat(), "figures": out}


def freeze(session, org_id: str, *, entity_ids=None, period_end: date) -> dict:
    """Everything the ESRS statement filing prints and its checks read, for the undertaking the filing is for."""
    from sqlalchemy import text

    from services.calc_settings import get_calc_settings
    from services.governance import csrd_roles, csrd_scope, esrs_statement
    from services.governance.entities import root_of
    from services.governance.period_close import is_closed
    entity = root_of(session, org_id, entity_ids)
    spec = governing(session, org_id, period_end)
    statement = esrs_statement.compute(session, org_id, entity_id=entity, period_end=period_end, esrs_version=spec["version"])
    provided = _provided(session, org_id, entity, period_end)
    ans = answers(session, org_id, entity, period_end)
    role = csrd_roles.live_role(session, org_id, entity, period_end)
    kind = role["role"] if role and role["role"] in ("individual", "consolidated") else None
    has_entities = bool(session.execute(text("SELECT 1 FROM reporting_entities WHERE org_id = CAST(:o AS uuid) LIMIT 1"),
                                        {"o": org_id}).first())
    previous = _previous(session, org_id, entity, period_end)
    sections = build(spec, statement, provided, ans)
    for sec in sections:                                    # each figure beside its previous-period figure
        for i in sec["items"]:
            for d in i.get("datapoints") or []:
                c = d.get("concept")
                if isinstance(c, str):
                    d["previous"] = (previous["figures"].get(c) or {}).get("value")
    return {"document_report": {
        "esrs_version": spec["version"], "period_end": period_end.isoformat(), "reporting_entity_id": entity,
        "org_has_entities": has_entities, "role": role,
        "scope_check": csrd_scope.check(session, org_id, entity, period_end, kind, get_calc_settings(session, org_id)),
        "period_closed": is_closed(session, org_id, entity, period_end), "statement": statement,
        "provided": provided, "answers": ans, "previous": previous, "sections": sections}}


# ───────────────────────────── the filed form: what a reader sees ─────────────────────────────

_REASON = {"not_material": "not material", "condition_not_applicable": "its condition does not apply", "phase_in": "phase-in"}


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v:,.10g}"
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_fmt(x)}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(_fmt(x) for x in v)
    return "—" if v is None else str(v)


def _shown(i: dict) -> dict:
    """One statement item in the shared document shape (web SfdrDocumentItems.DocItem)."""
    if i["status"] == "printed":
        return {"id": i["id"], "kind": i["kind"], "label": i["label"], "parent": i.get("parent"), "source": "fixed",
                "status": "printed"}
    if i["status"] == "omitted":
        om = i["omission"]
        why = _REASON[om["reason"]] + (f" ({om['phase_in']})" if om.get("phase_in") else "") + \
            (" — the topic is assessed not material" if om.get("scope") == "topic" else "")
        return {"id": i["id"], "kind": i["kind"], "label": i["label"], "parent": i.get("parent"), "source": "input",
                "status": "filled", "value": {"text": om.get("statement")} if om.get("statement") else None,
                "note": f"Omitted: {why}"}
    lines = []
    for d in i.get("datapoints") or []:
        v = d.get("by_horizon") or d.get("value")
        cur = f" {d['currency']}" if d.get("currency") else (f" {d['unit']}" if d.get("unit") and d["unit"] not in ("count", "boolean") else "")
        prev = f" (previous period: {_fmt(d['previous'])})" if d.get("previous") is not None else ""
        lines.append(f"{d['key']}: {_fmt(v)}{cur}{prev}" if d["status"] != "missing" and d["status"] != "gap"
                     else f"{d['key']}: {d.get('gap') or 'not stated'}")
    a = i.get("answer") or {}
    text = "\n".join([*lines, *([a["text"]] if a.get("text") else [])]) or None
    computed = i["kind"] == "field" and all(d["lane"] in ("computed", "derived", "same_as") for d in i.get("datapoints") or [])
    return {"id": i["id"], "kind": i["kind"], "label": i["label"], "parent": i.get("parent"),
            "source": "computed" if computed else "input", "status": i["status"],
            "value": ({"text": text} if text else (a or None)) if i["kind"] == "field" else (a or None),
            "note": i.get("note")}


def sections(payload: dict) -> list[dict]:
    """The official-form tab: each standard of the frozen statement, item by item, in the regulation's order."""
    doc = payload.get("document_report") or {}
    rec = (payload.get("_specs") or {}).get("esrs") or {}
    if not doc.get("sections") or not rec.get("version"):
        return []
    spec = R.load(FAMILY, rec["version"])
    out = []
    for sec in doc["sections"]:
        topic = sec.get("topic") or {}
        note = ("Assessed not material" + (f": {topic['explanation']}" if topic.get("explanation") else "") + "."
                if topic.get("material") is False else "Assessed material." if topic.get("material") else
                "Materiality not stated.")
        out.append({"title": f"{sec['title']} ({R.citation(spec, sec['standard'])})", "key": f"esrs_{sec['standard']}",
                    "kind": "document", "columns": [], "rows": [], "items": [_shown(i) for i in sec["items"]], "note": note,
                    "spec": {"framework": FAMILY, "version": rec["version"], "template": sec["standard"],
                             "sha256": spec.get("_sha256")}})
    return out


def form(payload: dict) -> list[dict]:
    """The datapoint list: who reports, on which basis, and how far each standard is filled."""
    doc = payload.get("document_report") or {}
    if not doc.get("sections"):
        return []
    role, sc, st = doc.get("role") or {}, doc.get("scope_check") or {}, doc.get("statement") or {}
    head = [{"label": "Version", "value": doc.get("esrs_version")},
            {"label": "Financial year ending", "value": doc.get("period_end")},
            {"label": "CSRD role", "value": role.get("role") or "not stated"},
            {"label": "Required under Art. 5(2)", "value": {True: "yes", False: "no", None: "not determinable"}[sc.get("required")],
             "note": sc.get("reason") or (f"point {sc['point']}" if sc.get("point") else "")},
            {"label": "Sites in scope", "value": str(len(st.get("sites") or []))},
            {"label": "Reporting period closed", "value": "yes" if doc.get("period_closed") else "no"}]
    out = [{"section": "Undertaking and basis", "rows": head}]
    for sec in doc["sections"]:
        rows = [i for i in sec["items"] if i["status"] != "printed"]
        n = {k: sum(1 for i in rows if i["status"] == k) for k in ("filled", "omitted", "missing")}
        out.append({"section": f"ESRS {sec['standard']}", "rows": [
            {"label": "Items filled", "value": str(n["filled"])}, {"label": "Items omitted with a reason", "value": str(n["omitted"])},
            {"label": "Items missing", "value": str(n["missing"])}]})
    return out
