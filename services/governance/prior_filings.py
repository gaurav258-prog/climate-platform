"""Prior filings — store a customer's already-filed ESG reports as their reported track record, and read
them back for trends. Upload parses the submitted file into reported lines held as a draft; the preparer
confirms the read figures, which locks the filing and its figures as reported actuals (append-only, kept
separate from Tellumen's modelled figures and from Lane-2 provided values)."""
from __future__ import annotations

import hashlib
import re as _re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.governance.datapoint_catalog import catalog
from services.ingest import filing_import


class FilingError(Exception):
    pass


def _dp_label(framework: str, key: str) -> str:
    if framework == "esrs_pack":
        from services.governance.esrs_binding import concepts
        return (concepts().get(key) or {}).get("label", key)
    if framework == "bank_tcfd":                       # a Template 0 cell (bank_taxonomy_report.prior_targets)
        from services.governance.bank_taxonomy_report import prior_targets
        return prior_targets().get(key, key)
    if framework == "sfdr_pai":                        # a Table 1-3 row (sfdr_binding.prior_targets)
        from datetime import date as _d

        from services.governance.sfdr_binding import prior_targets as sfdr_targets
        return sfdr_targets(_d.today()).get(key, key)
    for dp in (catalog(framework) or []):
        if dp["key"] == key:
            return dp["label"]
    return key


def _esrs_sectors() -> list[str]:
    from services.governance.filings import FRAMEWORKS as REPORTS
    return list(REPORTS["esrs_pack"]["sectors"])


# Frameworks a customer can bring a prior filing for — professional, customer-facing labels. A retired one keeps its
# confirmed filings readable and takes no new upload (its lines were mapped to coarse keys that added different
# quantities together); an ESRS statement's lines are mapped to the concepts its year's version prints.
FRAMEWORKS: list[dict] = [
    {"key": "bank_p3esg", "label": "Pillar 3 ESG risk disclosures", "sectors": ["bank"]},
    {"key": "csrd_e1",    "label": "CSRD / ESRS E1 — climate (retired)", "sectors": []},
    {"key": "esrs_pack",  "label": "ESRS sustainability statement (E1 · E3 · E4)", "sectors": None},
    {"key": "sfdr_pai",   "label": "SFDR principal adverse impacts", "sectors": ["asset_manager"]},
    # the credit institution's EU Taxonomy Art. 8 report (the key keeps its historical name): its lines map to the cells
    # of the Summary of KPIs of the version governing the year (E95)
    {"key": "bank_tcfd",  "label": "EU Taxonomy Art. 8 — credit institutions (Summary of KPIs)", "sectors": ["bank"]},
]
_LABEL = {f["key"]: f["label"] for f in FRAMEWORKS}


def frameworks_for(org_type: str) -> list[dict]:
    return [{"key": f["key"], "label": f["label"]} for f in FRAMEWORKS
            if org_type in (f["sectors"] if f["sectors"] is not None else _esrs_sectors())]


def esrs_targets(session, org_id: str, period_end) -> dict[str, str]:
    """The ESRS concepts a filed statement for the financial year ending `period_end` can report (concept → label): every
    concept its governing version prints, except a breakdown (a line is one figure, not a breakdown's members)."""
    from services.governance import esrs_document as D
    from services.governance.esrs_binding import concepts, concepts_of
    try:
        spec = D.governing(session, org_id, period_end)
    except D.DocumentError as e:
        raise FilingError(str(e)) from e
    cs = concepts()
    return {k: cs[k]["label"] for k in sorted(concepts_of(spec)) if not cs[k].get("breakdown")}


def _targets(session, org_id: str, framework: str, period_end) -> dict[str, str] | None:
    """The cells a line may be mapped to, chosen by the version governing the year — an ESRS statement's concepts, a
    Taxonomy report's Summary of KPIs cells, an SFDR PAI statement's Table 1-3 rows; None for a framework mapped by its
    catalog keywords."""
    if framework not in ("esrs_pack", "bank_tcfd", "sfdr_pai"):
        return None
    if period_end is None:
        raise FilingError("The version is chosen by the financial year — give the period end (or a year in the label).")
    if framework == "sfdr_pai":                     # the Table 1-3 rows the statement's own figures use
        from services.governance.sfdr_binding import prior_targets as sfdr_targets
        return sfdr_targets(period_end)
    if framework == "bank_tcfd":
        from services.governance.bank_taxonomy_report import prior_targets
        return prior_targets(period_end)
    return esrs_targets(session, org_id, period_end)


def datapoints(framework: str, *, session=None, org_id: Optional[str] = None, period_end=None) -> list[dict]:
    """The datapoints a reported line can be mapped to, for the confirm-time remap control (an ESRS statement, a
    Taxonomy report: the cells of the version governing its year — period_end required)."""
    targets = _targets(session, org_id, framework, period_end)
    if targets is not None:
        return [{"key": k, "label": lb} for k, lb in targets.items()]
    return [{"key": dp["key"], "label": dp["label"]} for dp in (catalog(framework) or [])]


def create_from_upload(session, org_id: str, user_id: Optional[str], *, framework: str,
                       period_label: str, entity_name: Optional[str], filename: str, data: bytes,
                       currency: Optional[str] = None, period_end: Optional[str] = None,
                       undertaking: Optional[str] = None) -> dict:
    """currency: the currency the filing's money is reported in — resolves shared symbols ('$', '£', '¥') the file
    uses; never assumed. period_end: the date the period ends — stated, never taken from the label (E123).
    undertaking: whom the filed report is for — 'organisation' or one of the organisation's reporting entities — so
    its figures can be the previous period's of that undertaking (ESRS 1 §83-84); entity_name is kept as printed."""
    from datetime import date as _date

    from services.ingest.units import resolve_declared
    from services.reference.iso4217 import codes
    if framework not in _LABEL:
        raise FilingError("Unknown framework.")
    from services.governance.filings import retirement
    retired = retirement(framework)
    if retired:
        succ = retired.get("replaced_by")
        raise FilingError(f"{_LABEL[framework]} takes no new filings — "
                          + (f"upload it as {_LABEL[succ]}." if succ in _LABEL else f"it is retired since {retired['since']}."))
    if not period_label or not period_label.strip():
        raise FilingError("A reporting period is required.")
    ccy = (currency or "").strip().upper() or None
    if ccy and ccy not in codes():
        raise FilingError(f"'{ccy}' is not an ISO 4217 currency code.")
    if not period_end:
        raise FilingError("State the date the reporting period ends (YYYY-MM-DD).")
    try:
        pe = _date.fromisoformat(str(period_end)[:10])
    except ValueError:
        raise FilingError("The period end must be a date (YYYY-MM-DD).")
    entity_id = _undertaking(session, org_id, undertaking)
    targets = _targets(session, org_id, framework, pe)
    try:
        read = filing_import.extract(framework, filename, data, targets)
        for c in read["cells"]:
            c["unit"] = resolve_declared(c["unit"], ccy)
    except ValueError as e:
        code = str(e)
        raise FilingError({
            "unsupported_format": "That file type isn't supported. Upload the filing as XBRL, iXBRL, PDF or Excel.",
            "unreadable": "No reported figures could be read from that file. Check it is the filed report itself.",
            "unknown_framework": "Unknown framework.",
        }.get(code, "The file could not be read."))

    sha = hashlib.sha256(data).hexdigest()
    fid = session.execute(text("""
        INSERT INTO reported_filing (org_id, framework, period_label, entity_name, file_format,
            original_filename, file_bytes, file_sha256, file_size, n_lines, status, uploaded_by, currency, period_end,
            entity_id, undertaking_stated, period_end_stated)
        VALUES (:org, :fw, :pl, :ent, :fmt, :fn, :bytes, :sha, :sz, :n, 'draft', :uid, :ccy, :pe, CAST(:eid AS uuid), true, true)
        RETURNING filing_id
    """), {"org": org_id, "fw": framework, "pl": period_label.strip(), "ent": entity_name, "ccy": ccy, "pe": pe,
           "fmt": read["format"], "fn": filename, "bytes": data, "sha": sha, "sz": len(data),
           "n": read["n_total"], "uid": user_id, "eid": entity_id}).scalar()

    for c in read["cells"]:
        session.execute(text("""
            INSERT INTO reported_figure (filing_id, org_id, framework, period_label, template_ref,
                datapoint_key, label, value_num, value_text, unit, read_method, confirmed)
            VALUES (:fid, :org, :fw, :pl, :tref, :dk, :lbl, :vn, :vt, :unit, 'auto', false)
        """), {"fid": fid, "org": org_id, "fw": framework, "pl": period_label.strip(),
               "tref": c["template_ref"], "dk": c["datapoint_key"], "lbl": c["label"][:1000],
               "vn": c["value_num"], "vt": c["value_text"], "unit": c["unit"]})
    session.commit()
    return get_filing(session, str(fid), org_id)


def _undertaking(session, org_id: str, undertaking: Optional[str]) -> Optional[str]:
    """'organisation' → None; an entity id of this organisation → itself; anything else refused (never inferred)."""
    if undertaking == "organisation":
        return None
    if not undertaking:
        raise FilingError("State whom the filed report is for: the organisation or one of its entities.")
    ok = session.execute(text("SELECT 1 FROM reporting_entities WHERE entity_id = CAST(:e AS uuid) AND org_id = CAST(:o AS uuid)"),
                         {"e": undertaking, "o": org_id}).first()
    if not ok:
        raise FilingError("That undertaking is not one of this organisation's entities.")
    return undertaking


def state_basis(session, org_id: str, filing_id: str, *, undertaking: str, period_end: str) -> dict:
    """For a filing uploaded before the undertaking and period end were stated (E123): state both, once."""
    from datetime import date as _date
    f = session.execute(text("""SELECT undertaking_stated, period_end_stated FROM reported_filing
                                WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""),
                        {"f": filing_id, "o": org_id}).mappings().first()
    if not f:
        raise FilingError("Filing not found.")
    if f["undertaking_stated"] and f["period_end_stated"]:
        raise FilingError("Its undertaking and period end are already stated.")
    try:
        pe = _date.fromisoformat(str(period_end)[:10])
    except ValueError:
        raise FilingError("The period end must be a date (YYYY-MM-DD).")
    eid = _undertaking(session, org_id, undertaking)
    try:
        with session.begin_nested():
            session.execute(text("""UPDATE reported_filing SET entity_id = CAST(:e AS uuid), undertaking_stated = true,
                                    period_end = :pe, period_end_stated = true WHERE filing_id = CAST(:f AS uuid)"""),
                            {"e": eid, "pe": pe, "f": filing_id})
    except IntegrityError:                  # one confirmed filing per undertaking and period (prior_undertaking_20261002)
        raise FilingError("A confirmed filing of that undertaking for that period already exists — remove one of them first.")
    return get_filing(session, filing_id, org_id)


def reported_figures(session, org_id: str, framework: str, entity_id: Optional[str], period_end) -> dict:
    """The figures a confirmed prior filing of this undertaking reported for the period ending on that date —
    {datapoint_key: {value, filing_id}} — from filings whose undertaking and period end are stated (E123)."""
    rows = session.execute(text("""
        SELECT f.filing_id::text AS fid, g.datapoint_key, g.value_num, g.value_text
        FROM reported_filing f JOIN reported_figure g USING (filing_id)
        WHERE f.org_id = CAST(:o AS uuid) AND f.framework = :fw AND f.status = 'confirmed'
          AND f.undertaking_stated AND f.period_end_stated AND f.period_end = :pe
          AND f.entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND g.datapoint_key IS NOT NULL
        ORDER BY g.seq"""), {"o": org_id, "fw": framework, "pe": period_end, "e": entity_id}).mappings().all()
    return {r["datapoint_key"]: {"value": r["value_num"] if r["value_num"] is not None else r["value_text"],
                                 "filing_id": r["fid"]} for r in rows}


def list_filings(session, org_id: str, framework: Optional[str] = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT filing_id, framework, period_label, entity_name, file_format, original_filename,
               status, n_lines, uploaded_at, confirmed_at, period_end, entity_id::text AS entity_id, undertaking_stated,
               period_end_stated
        FROM reported_filing
        WHERE org_id = :org AND (CAST(:fw AS text) IS NULL OR framework = :fw)
        ORDER BY period_label DESC, uploaded_at DESC, filing_id
    """), {"org": org_id, "fw": framework}).mappings().all()
    return [{
        "filing_id": str(r["filing_id"]), "framework": r["framework"],
        "framework_label": _LABEL.get(r["framework"], r["framework"]),
        "period_label": r["period_label"], "entity_name": r["entity_name"],
        "file_format": r["file_format"], "original_filename": r["original_filename"],
        "status": r["status"], "n_lines": r["n_lines"],
        "uploaded_at": r["uploaded_at"].isoformat() if r["uploaded_at"] else None,
        "confirmed_at": r["confirmed_at"].isoformat() if r["confirmed_at"] else None,
        "period_end": r["period_end"].isoformat() if r["period_end"] else None, "entity_id": r["entity_id"],
        "undertaking_stated": r["undertaking_stated"], "period_end_stated": r["period_end_stated"],
    } for r in rows]


def get_filing(session, filing_id: str, org_id: str) -> dict:
    f = session.execute(text("""
        SELECT filing_id, framework, period_label, period_end, entity_name, file_format, original_filename,
               file_sha256, basis_note, status, n_lines, uploaded_at, confirmed_at, entity_id::text AS entity_id,
               undertaking_stated, period_end_stated
        FROM reported_filing WHERE filing_id = :fid AND org_id = :org
    """), {"fid": filing_id, "org": org_id}).mappings().first()
    if not f:
        raise FilingError("Filing not found.")
    figs = session.execute(text("""
        SELECT figure_id, template_ref, datapoint_key, label, value_num, value_text, unit,
               read_method, confirmed
        FROM reported_figure WHERE filing_id = :fid ORDER BY seq
    """), {"fid": filing_id}).mappings().all()
    return {
        "filing_id": str(f["filing_id"]), "framework": f["framework"],
        "framework_label": _LABEL.get(f["framework"], f["framework"]),
        "period_label": f["period_label"], "entity_name": f["entity_name"],
        "period_end": f["period_end"].isoformat() if f["period_end"] else None, "entity_id": f["entity_id"],
        "undertaking_stated": f["undertaking_stated"], "period_end_stated": f["period_end_stated"],
        "file_format": f["file_format"], "original_filename": f["original_filename"],
        "file_sha256": f["file_sha256"], "basis_note": f["basis_note"], "status": f["status"],
        "n_lines": f["n_lines"],
        "uploaded_at": f["uploaded_at"].isoformat() if f["uploaded_at"] else None,
        "confirmed_at": f["confirmed_at"].isoformat() if f["confirmed_at"] else None,
        "figures": [{
            "figure_id": str(r["figure_id"]), "template_ref": r["template_ref"],
            "datapoint_key": r["datapoint_key"], "label": r["label"],
            "value_num": r["value_num"], "value_text": r["value_text"], "unit": r["unit"],
            "read_method": r["read_method"], "confirmed": r["confirmed"],
        } for r in figs],
    }


def confirm(session, filing_id: str, org_id: str, user_id: Optional[str], *,
            edits: Optional[list[dict]] = None, basis_note: Optional[str] = None) -> dict:
    """Lock a draft filing: apply any corrected values, then mark the filing and its figures confirmed.
    An edited value is recorded as read_method 'confirmed'. One confirmed filing per undertaking and period end
    (per period label for a filing whose undertaking and period end are not yet stated)."""
    f = session.execute(text("""
        SELECT status FROM reported_filing WHERE filing_id = :fid AND org_id = :org
    """), {"fid": filing_id, "org": org_id}).mappings().first()
    if not f:
        raise FilingError("Filing not found.")
    if f["status"] == "confirmed":
        raise FilingError("This filing is already confirmed and cannot be changed.")
    _check_esrs_mapping(session, filing_id, org_id, edits or [])

    for e in (edits or []):
        gid = e.get("figure_id")
        if not gid:
            continue
        if e.get("drop"):
            session.execute(text("DELETE FROM reported_figure WHERE figure_id = :g AND filing_id = :fid"),
                            {"g": gid, "fid": filing_id})
            continue
        sets, params = [], {"g": gid, "fid": filing_id}
        if "value_num" in e:
            sets.append("value_num = :vn"); params["vn"] = e["value_num"]
        if "value_text" in e:
            sets.append("value_text = :vt"); params["vt"] = e["value_text"]
        if "datapoint_key" in e:
            sets.append("datapoint_key = :dk"); params["dk"] = e["datapoint_key"] or None
        if "unit" in e:                                  # the preparer can correct what the reader took the unit to be
            from services.ingest.units import normalise
            sets.append("unit = :u"); params["u"] = normalise(e["unit"])
        if sets:
            sets.append("read_method = 'confirmed'")
            session.execute(text(f"UPDATE reported_figure SET {', '.join(sets)} "
                                 f"WHERE figure_id = :g AND filing_id = :fid"), params)

    session.execute(text("UPDATE reported_figure SET confirmed = true WHERE filing_id = :fid"),
                    {"fid": filing_id})
    try:
        session.execute(text("""
            UPDATE reported_filing
               SET status = 'confirmed', confirmed_by = :uid, confirmed_at = now(),
                   basis_note = COALESCE(:bn, basis_note),
                   n_lines = (SELECT count(*) FROM reported_figure WHERE filing_id = :fid)
             WHERE filing_id = :fid AND org_id = :org
        """), {"uid": user_id, "bn": basis_note, "fid": filing_id, "org": org_id})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise FilingError("A confirmed filing already exists for that framework, undertaking and period. "
                          "Remove it before confirming a replacement.")
    return get_filing(session, filing_id, org_id)


def _check_esrs_mapping(session, filing_id: str, org_id: str, edits: list[dict]) -> None:
    """An ESRS statement's lines map to the concepts its year's version prints, each concept at most once (two lines on
    one concept would be added together as one figure). Read with the edits applied, and refused before any is written."""
    f = session.execute(text("SELECT framework, period_end FROM reported_filing WHERE filing_id = :fid"),
                        {"fid": filing_id}).mappings().first()
    targets = _targets(session, org_id, f["framework"], f["period_end"])
    if targets is None:
        return
    mapped = {str(r[0]): r[1] for r in session.execute(text(
        "SELECT figure_id, datapoint_key FROM reported_figure WHERE filing_id = :fid"), {"fid": filing_id}).all()}
    for e in edits:
        if e.get("figure_id") in mapped:
            if e.get("drop"):
                mapped.pop(e["figure_id"])
            elif "datapoint_key" in e:
                mapped[e["figure_id"]] = e["datapoint_key"] or None
    keys = [k for k in mapped.values() if k]
    unknown = sorted({k for k in keys if k not in targets})
    twice = sorted({k for k in keys if keys.count(k) > 1})
    if unknown or twice:
        raise FilingError("; ".join(
            ([f"not a figure the version for this year prints: {', '.join(unknown)}"] if unknown else []) +
            ([f"more than one line is mapped to {', '.join(twice)} — keep one"] if twice else [])))


def delete_filing(session, filing_id: str, org_id: str) -> None:
    n = session.execute(text("DELETE FROM reported_filing WHERE filing_id = :fid AND org_id = :org"),
                        {"fid": filing_id, "org": org_id}).rowcount
    session.commit()
    if not n:
        raise FilingError("Filing not found.")


def _project(points: list[dict], horizon_years: int) -> dict:
    """Continue a reported series forward from its LAST confirmed value, so reported→projected is continuous.
    Rate is taken from the customer's own reported history: compound annual change when values are same-sign
    and positive, otherwise the average annual change. Returns [] when the periods aren't plain years or
    there are fewer than two points (nothing to extrapolate from)."""
    yrs, vals = [], []
    for p in points:
        m = _re.search(r"(19|20)\d{2}", p["period"] or "")
        if not m or p["value"] is None:
            return {"projection": [], "method": None}
        yrs.append(int(m.group(0))); vals.append(float(p["value"]))
    if len(vals) < 2:
        return {"projection": [], "method": None}
    span = yrs[-1] - yrs[0]
    first, last = vals[0], vals[-1]
    if span > 0 and first > 0 and last > 0:
        rate = (last / first) ** (1 / span) - 1
        proj = [{"period": str(yrs[-1] + k), "value": last * (1 + rate) ** k, "projected": True}
                for k in range(1, horizon_years + 1)]
        method = "compound annual change from your reported history"
    else:
        delta = (last - first) / span if span else 0.0
        proj = [{"period": str(yrs[-1] + k), "value": last + delta * k, "projected": True}
                for k in range(1, horizon_years + 1)]
        method = "average annual change from your reported history"
    return {"projection": proj, "method": method}


def trends(session, org_id: str, framework: Optional[str] = None, horizon_years: int = 3) -> dict:
    """All reported-figure series across confirmed filings — one series per (framework, datapoint), its value
    per period, and a flag where the stated preparation basis changed between periods (so a trend is never
    drawn as continuous across a methodology or boundary change). Each series also carries a forward
    projection continuing from its last confirmed value."""
    horizon_years = max(1, min(10, horizon_years))
    ccy = _presentation(session, org_id)
    rows = _figures(session, org_id, framework, None)
    series: dict[tuple, dict] = {}
    for (fw, dk, period), figs in _grouped(rows).items():
        s = series.setdefault((fw, dk), {
            "framework": fw, "framework_label": _LABEL.get(fw, fw),
            "datapoint_key": dk, "label": _dp_label(fw, dk), "points": [],
        })
        s["points"].append({**_combine(session, figs, ccy), "period": period, "basis_note": figs[0]["basis_note"]})

    out = []
    for s in series.values():
        bases = [p["basis_note"] or "" for p in s["points"]]
        # mark each point where its basis — or its unit — differs from the prior period's (a discontinuity)
        for i, p in enumerate(s["points"]):
            p["basis_break"] = i > 0 and bases[i] != bases[i - 1]
            p["unit_break"] = i > 0 and p["unit"] != s["points"][i - 1]["unit"]
        s["basis_changed"] = len({b for b in bases if b}) > 1 or any(p["basis_break"] for p in s["points"])
        s["unit_changed"] = any(p["unit_break"] for p in s["points"])
        s["mixed_units"] = any(p.get("mixed_units") for p in s["points"])
        comparable = not (s["unit_changed"] or s["mixed_units"])
        pr = _project(s["points"], horizon_years) if comparable else {"projection": [], "method": None}
        s["projection"] = pr["projection"]
        s["proj_method"] = pr["method"]
        s["proj_reliable"] = bool(pr["projection"]) and not s["basis_changed"]
        out.append(s)
    out.sort(key=lambda s: (-len(s["points"]), s["label"]))
    return {"series": out, "currency": ccy}


# ── units (multi-currency phase 4, 2026-09-27) ──────────────────────────────────────────────────────────────────
# A datapoint's figures in one period used to be summed whatever their units (€ with $ with tCO2e) and labelled with
# the alphabetically largest unit. Now: money in different currencies is converted to the organisation's presentation
# currency at the closing rate of the period end before it is added; figures in different non-money units — or money
# with figures whose unit is unknown — are NOT added: the point is shown as mixed, with each unit's own total.

def _presentation(session, org_id: str) -> str:
    from services.governance.reporting_settings import get_settings
    return get_settings(session, org_id)["presentation_currency"]


def _figures(session, org_id: str, framework: Optional[str], datapoint_key: Optional[str]) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT g.framework, g.datapoint_key, rf.period_label, rf.period_end, rf.period_end_stated, rf.basis_note,
               g.value_num, g.unit
        FROM reported_figure g JOIN reported_filing rf ON rf.filing_id = g.filing_id
        WHERE g.org_id = :org AND rf.status = 'confirmed' AND g.datapoint_key IS NOT NULL AND g.value_num IS NOT NULL
              AND (CAST(:fw AS text) IS NULL OR g.framework = :fw) AND (CAST(:dk AS text) IS NULL OR g.datapoint_key = :dk)
        ORDER BY g.framework, g.datapoint_key, rf.period_label
    """), {"org": org_id, "fw": framework, "dk": datapoint_key}).mappings()]


def _grouped(rows: list[dict]) -> dict:
    out: dict[tuple, list] = {}
    for r in rows:
        out.setdefault((r["framework"], r["datapoint_key"], r["period_label"]), []).append(r)
    return out


def _period_end(fig: dict):
    """The stated period end — never a date read from the label (E123); not stated → money is not converted."""
    return fig["period_end"] if fig.get("period_end_stated") else None


def _combine(session, figs: list[dict], ccy: str) -> dict:
    """One period's figures for one datapoint → {value, unit, …}. Money is converted to `ccy` (closing rate on the
    period end); anything else is only added to figures in the same unit."""
    from services.ingest.units import is_ambiguous_money, is_currency
    from services.reference.fx import FxError, rate_for
    by_unit: dict = {}
    for f in figs:
        by_unit[f["unit"]] = by_unit.get(f["unit"], 0.0) + float(f["value_num"])
    shared = sorted(u for u in by_unit if is_ambiguous_money(u))
    if shared:                        # '$' could be several currencies: not used until the filing's currency is stated
        return {"value": None, "unit": None, "mixed_units": sorted(str(u) for u in by_unit),
                "note": f"money written as {', '.join(shared)} — state the filing's currency (or the unit on confirm)"}
    money = {u: v for u, v in by_unit.items() if is_currency(u)}
    if money and len(money) == len(by_unit):
        if set(money) == {ccy}:
            return {"value": money[ccy], "unit": ccy}
        d = _period_end(figs[0])
        if d is None:
            return {"value": None, "unit": None, "mixed_units": sorted(money),
                    "note": "amounts in " + ", ".join(sorted(money)) + " — no period end to convert them at"}
        try:
            total = sum(v * rate_for(session, ccy, d)["units_per_eur"] / rate_for(session, u, d)["units_per_eur"]
                        for u, v in money.items())
        except FxError as e:
            return {"value": None, "unit": None, "mixed_units": sorted(money), "note": f"not converted: {e}"}
        return {"value": total, "unit": ccy, "converted_from": {u: round(v, 2) for u, v in money.items()},
                "rate_date": d.isoformat()}
    if len(by_unit) == 1:
        (u, v), = by_unit.items()
        return {"value": v, "unit": u}
    return {"value": None, "unit": None, "mixed_units": sorted(str(u) for u in by_unit),
            "by_unit": {str(u): round(v, 4) for u, v in by_unit.items()},
            "note": "figures in different units — not added together; correct the units or datapoints on confirm"}


def trend(session, org_id: str, framework: str, datapoint_key: str) -> dict:
    """Reported values for one datapoint across confirmed filings — the customer's own filed history."""
    ccy = _presentation(session, org_id)
    groups = _grouped(_figures(session, org_id, framework, datapoint_key))
    return {"framework": framework, "datapoint_key": datapoint_key, "currency": ccy,
            "points": [{**_combine(session, figs, ccy), "period": period} for (_, _, period), figs in groups.items()]}
