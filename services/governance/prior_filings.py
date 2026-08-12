"""Prior filings — store a customer's already-filed ESG reports as their reported track record, and read
them back for trends. Upload parses the submitted file into reported lines held as a draft; the preparer
confirms the read figures, which locks the filing and its figures as reported actuals (append-only, kept
separate from Tellumen's modelled figures and from Lane-2 provided values)."""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.ingest import filing_import
from services.governance.datapoint_catalog import catalog


class FilingError(Exception):
    pass


def _dp_label(framework: str, key: str) -> str:
    for dp in (catalog(framework) or []):
        if dp["key"] == key:
            return dp["label"]
    return key


# Frameworks a customer can bring a prior filing for — professional, customer-facing labels.
FRAMEWORKS: list[dict] = [
    {"key": "bank_p3esg", "label": "Pillar 3 ESG risk disclosures", "sectors": ["bank"]},
    {"key": "csrd_e1",    "label": "CSRD / ESRS E1 — climate", "sectors": ["bank", "asset_manager", "reit"]},
    {"key": "sfdr_pai",   "label": "SFDR principal adverse impacts", "sectors": ["asset_manager"]},
    {"key": "bank_tcfd",  "label": "TCFD climate disclosures", "sectors": ["bank", "asset_manager", "reit"]},
]
_LABEL = {f["key"]: f["label"] for f in FRAMEWORKS}


def frameworks_for(org_type: str) -> list[dict]:
    return [{"key": f["key"], "label": f["label"]} for f in FRAMEWORKS if org_type in f["sectors"]]


def create_from_upload(session, org_id: str, user_id: Optional[str], *, framework: str,
                       period_label: str, entity_name: Optional[str], filename: str, data: bytes) -> dict:
    if framework not in _LABEL:
        raise FilingError("Unknown framework.")
    if not period_label or not period_label.strip():
        raise FilingError("A reporting period is required.")
    try:
        read = filing_import.extract(framework, filename, data)
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
            original_filename, file_bytes, file_sha256, file_size, n_lines, status, uploaded_by)
        VALUES (:org, :fw, :pl, :ent, :fmt, :fn, :bytes, :sha, :sz, :n, 'draft', :uid)
        RETURNING filing_id
    """), {"org": org_id, "fw": framework, "pl": period_label.strip(), "ent": entity_name,
           "fmt": read["format"], "fn": filename, "bytes": data, "sha": sha, "sz": len(data),
           "n": read["n_total"], "uid": user_id}).scalar()

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


def list_filings(session, org_id: str, framework: Optional[str] = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT filing_id, framework, period_label, entity_name, file_format, original_filename,
               status, n_lines, uploaded_at, confirmed_at
        FROM reported_filing
        WHERE org_id = :org AND (CAST(:fw AS text) IS NULL OR framework = :fw)
        ORDER BY period_label DESC, uploaded_at DESC
    """), {"org": org_id, "fw": framework}).mappings().all()
    return [{
        "filing_id": str(r["filing_id"]), "framework": r["framework"],
        "framework_label": _LABEL.get(r["framework"], r["framework"]),
        "period_label": r["period_label"], "entity_name": r["entity_name"],
        "file_format": r["file_format"], "original_filename": r["original_filename"],
        "status": r["status"], "n_lines": r["n_lines"],
        "uploaded_at": r["uploaded_at"].isoformat() if r["uploaded_at"] else None,
        "confirmed_at": r["confirmed_at"].isoformat() if r["confirmed_at"] else None,
    } for r in rows]


def get_filing(session, filing_id: str, org_id: str) -> dict:
    f = session.execute(text("""
        SELECT filing_id, framework, period_label, entity_name, file_format, original_filename,
               file_sha256, basis_note, status, n_lines, uploaded_at, confirmed_at
        FROM reported_filing WHERE filing_id = :fid AND org_id = :org
    """), {"fid": filing_id, "org": org_id}).mappings().first()
    if not f:
        raise FilingError("Filing not found.")
    figs = session.execute(text("""
        SELECT figure_id, template_ref, datapoint_key, label, value_num, value_text, unit,
               read_method, confirmed
        FROM reported_figure WHERE filing_id = :fid ORDER BY created_at
    """), {"fid": filing_id}).mappings().all()
    return {
        "filing_id": str(f["filing_id"]), "framework": f["framework"],
        "framework_label": _LABEL.get(f["framework"], f["framework"]),
        "period_label": f["period_label"], "entity_name": f["entity_name"],
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
    An edited value is recorded as read_method 'confirmed'. One confirmed filing per (org, framework, period)."""
    f = session.execute(text("""
        SELECT status FROM reported_filing WHERE filing_id = :fid AND org_id = :org
    """), {"fid": filing_id, "org": org_id}).mappings().first()
    if not f:
        raise FilingError("Filing not found.")
    if f["status"] == "confirmed":
        raise FilingError("This filing is already confirmed and cannot be changed.")

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
            sets.append("datapoint_key = :dk"); params["dk"] = e["datapoint_key"]
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
        raise FilingError("A confirmed filing already exists for that framework and period. "
                          "Remove it before confirming a replacement.")
    return get_filing(session, filing_id, org_id)


def delete_filing(session, filing_id: str, org_id: str) -> None:
    n = session.execute(text("DELETE FROM reported_filing WHERE filing_id = :fid AND org_id = :org"),
                        {"fid": filing_id, "org": org_id}).rowcount
    session.commit()
    if not n:
        raise FilingError("Filing not found.")


def trends(session, org_id: str, framework: Optional[str] = None) -> dict:
    """All reported-figure series across confirmed filings — one series per (framework, datapoint), its value
    per period, and a flag where the stated preparation basis changed between periods (so a trend is never
    drawn as continuous across a methodology or boundary change)."""
    rows = session.execute(text("""
        SELECT g.framework, g.datapoint_key, rf.period_label,
               sum(g.value_num) AS value, max(g.unit) AS unit, max(rf.basis_note) AS basis_note
        FROM reported_figure g JOIN reported_filing rf ON rf.filing_id = g.filing_id
        WHERE g.org_id = :org AND rf.status = 'confirmed' AND g.datapoint_key IS NOT NULL
              AND g.value_num IS NOT NULL AND (CAST(:fw AS text) IS NULL OR g.framework = :fw)
        GROUP BY g.framework, g.datapoint_key, rf.period_label
        ORDER BY g.framework, g.datapoint_key, rf.period_label
    """), {"org": org_id, "fw": framework}).mappings().all()

    series: dict[tuple, dict] = {}
    for r in rows:
        key = (r["framework"], r["datapoint_key"])
        s = series.setdefault(key, {
            "framework": r["framework"], "framework_label": _LABEL.get(r["framework"], r["framework"]),
            "datapoint_key": r["datapoint_key"], "label": _dp_label(r["framework"], r["datapoint_key"]),
            "points": [],
        })
        s["points"].append({"period": r["period_label"], "value": r["value"],
                            "unit": r["unit"], "basis_note": r["basis_note"]})

    out = []
    for s in series.values():
        bases = [p["basis_note"] or "" for p in s["points"]]
        # mark each point where its basis differs from the prior period's (a discontinuity)
        for i, p in enumerate(s["points"]):
            p["basis_break"] = i > 0 and bases[i] != bases[i - 1]
        s["basis_changed"] = len({b for b in bases if b}) > 1 or any(p["basis_break"] for p in s["points"])
        out.append(s)
    out.sort(key=lambda s: (-len(s["points"]), s["label"]))
    return {"series": out}


def trend(session, org_id: str, framework: str, datapoint_key: str) -> dict:
    """Reported values for one datapoint across confirmed filings — the customer's own filed history."""
    rows = session.execute(text("""
        SELECT rf.period_label, sum(g.value_num) AS value, max(g.unit) AS unit
        FROM reported_figure g JOIN reported_filing rf ON rf.filing_id = g.filing_id
        WHERE g.org_id = :org AND g.framework = :fw AND g.datapoint_key = :dk
              AND rf.status = 'confirmed' AND g.value_num IS NOT NULL
        GROUP BY rf.period_label ORDER BY rf.period_label
    """), {"org": org_id, "fw": framework, "dk": datapoint_key}).mappings().all()
    return {"framework": framework, "datapoint_key": datapoint_key,
            "points": [{"period": r["period_label"], "value": r["value"], "unit": r["unit"]} for r in rows]}
