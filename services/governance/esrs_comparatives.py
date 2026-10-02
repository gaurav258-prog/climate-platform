"""Comparative information in an ESRS statement (ESRS 1 chapter 7.1), per the version governing the financial year:

  both    §83  comparative information for the previous period for every quantitative metric and amount
          §85  where it is impracticable (to adjust / revise) for a prior period, that fact is disclosed
  2023    §84  a comparative that differs from the figure reported in the previous period: (a) the difference and
               (b) the reasons for the revision
          §136 not required in the first year of preparation under the ESRS; for a phased-in Disclosure Requirement
               (Appendix C), the first year of its mandatory application
  2026    §87(a) comparative amounts that significantly differ from those reported: the reasons and the difference —
               whether a difference is significant is the undertaking's statement
          §87(b) a topic reported for the first time: no comparative information for it
          §124 wave one: not for its first year under Delegated Regulation (EU) 2026/1563 where the metric is not the same
               as one the first set (2023/2772) required; other undertakings: not for their first financial year

Facts (never assumed):
  reported    the figure reported for the previous period — the undertaking's statement filed for it (submitted or
              accepted), else a previous statement uploaded, stated as the undertaking's and confirmed (prior filings)
  comparative the undertaking's attested figure for the previous period where it states one (a revision when it differs
              from the reported one), else the reported figure
  first year  the attested csrd.first_reporting_year (the year the phase-ins also read); a wave is 'a' when that is a
              financial year starting before 2027 (2026/1563 ESRS 1 §122)
  same metric a concept the first set's version also prints (the concept registry — a declared reading: a concept is one
              metric across versions unless the registry gives the 2026 one its own key)

The undertaking's statements are template answers (family 'esrs', document 'comparatives', per undertaking and period):
'cmp.<concept>' — {"reason"} for a revision, {"significant": bool} (2026), {"impracticable": text};
'topic.<standard>' — {"first_time": true} (2026 §87(b)), refused where a previous statement shows the topic reported.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from services.governance import template_answers as TA

FAMILY, DOCUMENT = "esrs", "comparatives"
REPORTED = ("submitted", "accepted")


def is_2026(version: str) -> bool:
    return version.startswith("dr_2026")


def previous_end(period_end: date) -> date:
    from services.regspec import fy_start
    return fy_start(period_end) - timedelta(days=1)


def _numeric(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) or (
        isinstance(v, dict) and bool(v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values()))


def _reported(session, org_id: str, entity_id: str | None, prev_end: date) -> dict:
    """The previous period's statement as reported: {source, filing_id, figures {concept: value}, topics {std: material}}."""
    row = session.execute(text("""
        SELECT rf.filing_id::text AS fid, rf.status, rs.payload->'document_report'->'sections' AS sections
        FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = CAST(:o AS uuid) AND rf.framework = 'esrs_pack' AND rf.period_end = :pe
          AND rf.entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND rf.status = ANY(:st)
        ORDER BY rf.seq DESC LIMIT 1"""), {"o": org_id, "pe": prev_end, "e": entity_id, "st": list(REPORTED)}).mappings().first()
    if row:
        figs, topics = {}, {}
        for sec in row["sections"] or []:
            topics[sec["standard"]] = (sec.get("topic") or {}).get("material")
            for i in sec.get("items") or []:
                if i.get("status") == "omitted":
                    continue
                for d in i.get("datapoints") or []:
                    v = d.get("by_horizon") or d.get("value")
                    if isinstance(d.get("concept"), str) and _numeric(v):
                        figs[d["concept"]] = v
        return {"source": f"statement filed ({row['status']})", "filing_id": row["fid"], "figures": figs, "topics": topics}
    from services.governance.prior_filings import reported_figures
    up = reported_figures(session, org_id, "esrs_pack", entity_id, prev_end)
    if up:
        return {"source": "previous statement uploaded and confirmed", "filing_id": next(iter(up.values()))["filing_id"],
                "figures": {k: v["value"] for k, v in up.items() if _numeric(v["value"])}, "topics": None}
    return {"source": None, "filing_id": None, "figures": {}, "topics": None}


def _attested(session, org_id: str, entity_id: str | None, prev_end: date) -> dict:
    from services.governance.esrs_document import _provided
    out: dict = {}
    for k, v in _provided(session, org_id, entity_id, prev_end).items():
        concept, _, member = k.partition("@")
        if member:
            out.setdefault(concept, {})[member] = v["value"]
        else:
            out[concept] = v["value"]
    return {k: v for k, v in out.items() if _numeric(v)}


def _difference(reported, comparative):
    """revised comparative minus reported — per member for a breakdown."""
    if isinstance(reported, dict) and isinstance(comparative, dict):
        return {k: comparative.get(k, 0) - reported.get(k, 0) for k in sorted(set(reported) | set(comparative))}
    if isinstance(reported, (int, float)) and isinstance(comparative, (int, float)):
        return comparative - reported
    return None


def _differs(a, b) -> bool:
    return _difference(a, b) not in (None, 0, {}) and (not isinstance(_difference(a, b), dict)
                                                     or any(abs(x) > 1e-9 for x in _difference(a, b).values()))


def read(session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    return TA.read(session, org_id, FAMILY, DOCUMENT, entity_id=entity_id, period_end=period_end)


def _reliefs(session, org_id: str, spec: dict, period_end: date, facts: dict) -> dict:
    """Statement-level reliefs: {'all': reason | None, 'not_same_as_first_set': reason | None, 'needs': [facts]}."""
    from services.governance.esrs_document import DocumentError, governing
    from services.regspec import fy_start
    version, fy = spec["version"], fy_start(period_end).year
    first = facts.get("first_year")
    out = {"all": None, "not_same_as_first_set": None, "needs": []}
    if first is None:
        out["needs"].append("csrd.first_reporting_year")
        return out
    if not is_2026(version):
        if fy == int(first):
            out["all"] = "first year of preparation of the sustainability statement under the ESRS (2023 ESRS 1 §136)"
        return out
    if first > 2026:                                        # 'other undertakings' (2026/1563 ESRS 1 §122)
        if fy == int(first):
            out["all"] = "first financial year of reporting (2026 ESRS 1 §124, other undertakings)"
        return out
    try:
        prev_version = governing(session, org_id, previous_end(period_end))["version"]
    except DocumentError:
        prev_version = None
    if not (prev_version or "").startswith("dr_2026"):     # wave one's first year under 2026/1563
        out["not_same_as_first_set"] = ("first year of reporting under Delegated Regulation (EU) 2026/1563, a metric not "
                                        "the same as one the first set required (2026 ESRS 1 §124, wave one)")
    return out


def compute(session, org_id: str, entity_id: str | None, period_end: date, spec: dict, sections: list[dict],
            facts: dict) -> dict:
    """Each quantitative figure of the statement with its comparative and what the text requires of it; and what is
    still missing (for the checks)."""
    import services.regspec as R
    from services.governance.esrs_binding import concepts_of
    from services.governance.esrs_checks import phase_in_holds, phase_ins
    prev_end = previous_end(period_end)
    rep, att = _reported(session, org_id, entity_id, prev_end), _attested(session, org_id, entity_id, prev_end)
    ans = read(session, org_id, entity_id, period_end)
    rel = _reliefs(session, org_id, spec, period_end, facts)
    first_set = None
    if rel["not_same_as_first_set"]:
        first_set = concepts_of(R.load("esrs", "dr_2023_2772"))
    from services.regspec import fy_start
    fy = fy_start(period_end).year
    rules = phase_ins(spec["version"]) if not is_2026(spec["version"]) else []
    rows, missing = [], []
    for sec in sections:
        std, topic = sec["standard"], sec.get("topic") or {}
        if topic.get("material") is False:
            continue
        topic_first = None
        if is_2026(spec["version"]):
            if rep["topics"] is not None and rep["topics"].get(std) is not True:
                topic_first = "a topic reported for the first time (2026 ESRS 1 §87(b))"
            elif (ans.get(f"topic.{std}") or {}).get("first_time") and rep["topics"] is None:
                topic_first = "a topic reported for the first time, as the undertaking states (2026 ESRS 1 §87(b))"
        dr = None
        for i in sec["items"]:
            if i["kind"] == "heading":
                dr = i["id"]
                continue
            if i.get("status") == "omitted":
                continue
            for d in i.get("datapoints") or []:
                c, cur = d.get("concept"), d.get("by_horizon") or d.get("value")
                if not isinstance(c, str) or not _numeric(cur):
                    continue
                reported, attested = rep["figures"].get(c), att.get(c)
                comparative = attested if attested is not None else reported
                a = ans.get(f"cmp.{c}") or {}
                row = {"concept": c, "item": i["id"], "standard": std, "current": cur, "reported": reported,
                       "comparative": comparative, "source": "attested" if attested is not None else rep["source"],
                       "answer": a or None}
                relief = rel["all"] or topic_first or (rel["not_same_as_first_set"] if first_set is not None and c not in first_set
                                                       else None)
                if relief is None and rules:                 # 2023 §136: a phased-in DR's first year of mandatory application
                    for r in rules:
                        was, _ = phase_in_holds(r, i["id"], dr, std, i["kind"], fy - 1, facts)
                        now, _ = phase_in_holds(r, i["id"], dr, std, i["kind"], fy, facts)
                        if was is True and now is False:
                            relief = f"first year of mandatory application of a phased-in requirement ({r['id']}; 2023 ESRS 1 §136)"
                            break
                if comparative is None:
                    if relief:
                        row["status"] = "relief"
                        row["relief"] = relief
                    elif a.get("impracticable"):
                        row["status"] = "impracticable"
                    else:
                        row["status"] = "missing"
                        missing.append(f"{c} (§83)")
                elif reported is not None and attested is not None and _differs(reported, attested):
                    row["difference"] = _difference(reported, attested)
                    if is_2026(spec["version"]):
                        if "significant" not in a:
                            row["status"] = "state_significance"
                            missing.append(f"{c}: state whether the revised comparative differs significantly (2026 §87(a))")
                        elif a["significant"] and not a.get("reason"):
                            row["status"] = "reason_missing"
                            missing.append(f"{c}: the reasons for the change (2026 §87(a))")
                        else:
                            row["status"] = "revised"
                    elif not a.get("reason"):
                        row["status"] = "reason_missing"
                        missing.append(f"{c}: the reasons for the revision (2023 §84(b))")
                    else:
                        row["status"] = "revised"
                else:
                    row["status"] = "comparative"
                rows.append(row)
    return {"previous_period_end": prev_end.isoformat(), "reported": {k: rep[k] for k in ("source", "filing_id")},
            "reliefs": {k: rel[k] for k in ("all", "not_same_as_first_set")}, "needs": rel["needs"], "rows": rows,
            "missing": missing, "topics_first_time": {k: v for k, v in ans.items() if k.startswith("topic.")}}


def _validate(item: dict, value) -> dict:
    iid = item["id"]
    if not isinstance(value, dict):
        raise TA.AnswerError(f"{iid}: an answer is an object")
    if iid.startswith("topic."):
        if value.get("first_time") is not True:
            raise TA.AnswerError(f"{iid}: state {{'first_time': true}} for a topic reported for the first time")
        return {"first_time": True}
    out = {}
    if "significant" in value:
        if not isinstance(value["significant"], bool):
            raise TA.AnswerError(f"{iid}: significant is true or false")
        out["significant"] = value["significant"]
    for k in ("reason", "impracticable"):
        if str(value.get(k) or "").strip():
            out[k] = str(value[k]).strip()
    if not out:
        raise TA.AnswerError(f"{iid}: state the reasons, whether the difference is significant, or that a comparative is "
                             "impracticable")
    return out


def save(session, org_id: str, user_id: str, *, entity_id: str | None, period_end: date, spec: dict, sections: list[dict],
         answers: dict) -> dict:
    """The undertaking's statements on its comparatives for the period; a topic stated as reported for the first time is
    refused where a previous statement shows it reported, and only a 2026 statement has the §87(b) relief."""
    prev = _reported(session, org_id, entity_id, previous_end(period_end))
    items = [{"id": f"cmp.{d['concept']}", "kind": "field"} for sec in sections for i in sec["items"]
             for d in i.get("datapoints") or [] if isinstance(d.get("concept"), str)]
    topics = [{"id": f"topic.{sec['standard']}", "kind": "field"} for sec in sections] if is_2026(spec["version"]) else []
    for k, v in (answers or {}).items():
        if k.startswith("topic.") and v and prev["topics"] is not None and prev["topics"].get(k[6:]) is True:
            raise TA.AnswerError(f"{k}: the statement reported for {previous_end(period_end)} ({prev['source']}) reports "
                                 f"ESRS {k[6:]} — it is not reported for the first time")
    tmpl = {"items": list({i["id"]: i for i in items + topics}.values())}
    return TA.save(session, org_id, FAMILY, DOCUMENT, tmpl, {i["id"]: "input" for i in tmpl["items"]}, answers, user_id,
                   entity_id=entity_id, period_end=period_end, label="the statement's comparative information",
                   validate=_validate)
