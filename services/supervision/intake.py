"""Tier-2 intake — what a supervisor ingests about a supervised entity, and the shadow book it builds from it.

Two files per entity and period, both mapped column-by-column to the canonical fields the profile declares
(data/reference/supervision_profiles.json → sectors.<type>.intake), validate-before-save like every upload:
  • the SUBMITTED template (Pillar 3 Template 5 cells for a bank) → supervisor_submissions
  • the supervisor's own GRANULAR data (AnaCredit-style loan rows with a collateral region) → the SHADOW BOOK:
    rows in portfolio_entities on the regulator's org (source='supervisor_shadow', subject_org_id=<bank>), each
    located by services.geo.region_points (NUTS-3 / postcode→NUTS-3; country-only stays unlocated), then scored by
    the same on-demand path a bank's own upload uses. The portfolio engine then treats it as a book.
Nothing is fabricated: unresolved locations are counted and reported, never centred on a country.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import h3
from sqlalchemy import text

from services.geo.region_points import resolve as resolve_region
from services.ingest.upload_validation import parse_table
from services.supervision.lens import cell_key

_SYNONYMS = {
    "geography": ["geography", "country", "region", "geo", "nuts", "location"],
    "sector": ["sector", "nace", "nace_section", "industry", "counterparty_sector", "occupancy", "line_of_business", "lob",
              "property_type", "commodity", "issuer_sector"],
    "gross_carrying_amount_eur": ["gross_carrying_amount", "gross", "gca", "exposure", "carrying_amount", "total", "sum_insured", "tiv", "total_insured_value"],
    "sensitive_physical_eur": ["sensitive", "physical_risk", "of_which_sensitive", "sensitive_physical", "in_physical_risk_zones", "physical_risk_zones"],
    "sensitive_acute_eur": ["acute"], "sensitive_chronic_eur": ["chronic"], "maturity_bucket": ["maturity", "bucket", "tenor"],
    "instrument_id": ["instrument", "instrument_id", "contract", "loan_id", "id", "policy", "policy_id", "location_id"],
    "counterparty_name": ["counterparty", "debtor", "borrower", "name", "insured", "insured_name"],
    "nace_section": ["nace", "nace_code", "sector", "activity", "occupancy", "line_of_business", "lob"],
    "outstanding_eur": ["outstanding", "nominal", "amount", "balance", "exposure", "sum_insured", "si"],
    "maturity_date": ["maturity", "maturity_date", "final_maturity", "expiry", "policy_expiry"],
    "collateral_country": ["collateral_country", "protection_country", "country", "risk_country"],
    "collateral_nuts3": ["nuts3", "nuts", "collateral_nuts", "protection_nuts", "region_code", "risk_nuts3"],
    "collateral_postcode": ["postcode", "postal_code", "zip", "collateral_postcode", "protection_postcode", "cresta", "risk_postcode"],
    "collateral_value_eur": ["collateral_value", "protection_value", "collateral", "total_insured_value", "tiv"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def suggest_mapping(columns: list[str], fields: list[dict]) -> dict[str, Optional[str]]:
    """{canonical field id: file column or None} — exact normalised match first, then synonyms; never guesses
    the same column for two fields."""
    cols = {_norm(c): c for c in columns}
    out: dict[str, Optional[str]] = {}
    used: set[str] = set()
    for f in fields:
        fid = f["id"]; pick = None
        cands = [fid, _norm(f.get("label", ""))] + _SYNONYMS.get(fid, [])
        for c in cands:
            c = _norm(c)
            if c in cols and cols[c] not in used:
                pick = cols[c]; break
        if pick is None:
            for c in cands:
                c = _norm(c)
                for k, orig in cols.items():
                    if c and (k.startswith(c) or c in k.split("_")) and orig not in used:
                        pick = orig; break
                if pick:
                    break
        out[fid] = pick
        if pick:
            used.add(pick)
    return out


def _num(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).strip().replace("€", "").replace(" ", "")
    if not s or s.lower() in ("nan", "none", "-", "—"):
        return None
    if s.count(",") and s.count("."):
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif s.count(","):
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def map_rows(raw: bytes, filename: Optional[str], fields: list[dict], mapping: dict[str, Optional[str]]) -> dict:
    """Parse + map + validate. Returns {columns, rows (mapped dicts), errors:[{row, problems}], n_total, n_valid,
    missing_required:[field ids]} — the same shape a preparer previews and the import saves."""
    df = parse_table(raw, filename)
    columns = [str(c) for c in df.columns]
    missing = [f["id"] for f in fields if f.get("required") and not mapping.get(f["id"])]
    rows, errors = [], []
    for i, rec in enumerate(df.to_dict(orient="records")):
        row, problems = {}, []
        for f in fields:
            col = mapping.get(f["id"])
            v = rec.get(col) if col else None
            if isinstance(v, float) and v != v:
                v = None
            if f.get("type") == "number":
                n = _num(v)
                if v not in (None, "") and n is None:
                    problems.append(f"{f['label']}: not a number ({v!r})")
                v = n
            elif f.get("type") == "date" and v not in (None, ""):
                try:
                    v = v.date().isoformat() if hasattr(v, "date") else datetime.fromisoformat(str(v)[:10]).date().isoformat()
                except ValueError:
                    problems.append(f"{f['label']}: not a date ({v!r})"); v = None
            elif v is not None:
                v = str(v).strip() or None
            if f.get("required") and col and v in (None, ""):
                problems.append(f"{f['label']}: missing")
            row[f["id"]] = v
        (errors if problems else rows).append({"row": i + 2, "problems": problems} if problems else row)
    return {"columns": columns, "rows": rows, "errors": errors[:200], "n_total": len(df), "n_valid": len(rows),
            "n_error": len(errors), "missing_required": missing, "ok": not missing and len(rows) > 0}


# ── submitted template ────────────────────────────────────────────────────────────────────────────────────
def cells_from_rows(rows: list[dict]) -> dict[str, dict]:
    cells: dict[str, dict] = {}
    for r in rows:
        k = cell_key(r["geography"], r["sector"])
        c = cells.setdefault(k, {"geography": str(r["geography"]).strip().upper(), "sector": str(r["sector"]).strip().upper(),
                                 "gross_carrying_amount_eur": 0.0, "sensitive_physical_eur": 0.0,
                                 "sensitive_acute_eur": 0.0, "sensitive_chronic_eur": 0.0})
        for f in ("gross_carrying_amount_eur", "sensitive_physical_eur", "sensitive_acute_eur", "sensitive_chronic_eur"):
            c[f] += float(r.get(f) or 0)
    return cells


def save_submission(session, *, regulator_org_id: str, subject_org_id: str, framework: str, template: str, period_label: str,
                    basis: dict, cells: dict, raw: bytes, filename: Optional[str], mapping: dict, user_id: Optional[str],
                    channel: str = "supervisor_upload") -> dict:
    """channel: supervisor_upload (the supervisor keyed it in) | entity_portal (the entity submitted it) | api."""
    sha = hashlib.sha256(raw).hexdigest()
    session.execute(text("""
        INSERT INTO supervisor_submissions (regulator_org_id, subject_org_id, framework, template, period_label, basis, cells,
                                            n_cells, source_file, source_sha256, column_mapping, created_by, channel)
        VALUES (CAST(:r AS uuid), CAST(:s AS uuid), :fw, :tp, :p, CAST(:b AS jsonb), CAST(:c AS jsonb), :n, :f, :sha,
                CAST(:m AS jsonb), CAST(:u AS uuid), :ch)
        ON CONFLICT (regulator_org_id, subject_org_id, framework, template, period_label) DO UPDATE SET
            basis = EXCLUDED.basis, cells = EXCLUDED.cells, n_cells = EXCLUDED.n_cells, source_file = EXCLUDED.source_file,
            source_sha256 = EXCLUDED.source_sha256, column_mapping = EXCLUDED.column_mapping, created_by = EXCLUDED.created_by,
            channel = EXCLUDED.channel, created_at = now()
    """), {"r": regulator_org_id, "s": subject_org_id, "fw": framework, "tp": template, "p": period_label,
           "b": json.dumps(basis or {}), "c": json.dumps(cells), "n": len(cells), "f": filename, "sha": sha,
           "m": json.dumps(mapping), "u": user_id, "ch": channel})
    return {"framework": framework, "template": template, "period_label": period_label, "n_cells": len(cells), "sha256": sha}


def load_submission(session, regulator_org_id: str, subject_org_id: str, framework: str, template: str,
                    period_label: Optional[str] = None) -> Optional[dict]:
    row = session.execute(text(f"""
        SELECT period_label, basis, cells, n_cells, source_file, created_at FROM supervisor_submissions
        WHERE regulator_org_id = CAST(:r AS uuid) AND subject_org_id = CAST(:s AS uuid) AND framework = :fw AND template = :tp
        {"AND period_label = :p" if period_label else ""} ORDER BY created_at DESC LIMIT 1
    """), {"r": regulator_org_id, "s": subject_org_id, "fw": framework, "tp": template, "p": period_label}).mappings().first()
    return dict(row) if row else None


# ── shadow book ──────────────────────────────────────────────────────────────────────────────────────────
def _residual_years(maturity_iso: Optional[str]) -> Optional[float]:
    if not maturity_iso:
        return None
    try:
        return round(max(0.0, (date.fromisoformat(maturity_iso) - date.today()).days / 365.25), 2)
    except ValueError:
        return None


def _resolve_row_location(r: dict) -> Optional[dict]:
    """A granular row's location: the EUDR geolocation point (latitude/longitude) if the row carries one — the
    most precise source, used by the agri-food sourcing-plot extract — else the usual country/NUTS-3/postcode
    region resolution every other sector's granular data uses."""
    lat, lon = _num(r.get("latitude")), _num(r.get("longitude"))
    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        return {"lat": lat, "lon": lon, "name": None, "location_precision": "point"}
    return resolve_region(r.get("collateral_country"), r.get("collateral_nuts3"), r.get("collateral_postcode"))


def _get_or_create_commodity(session, name: str) -> str:
    """sc_commodities is the shared global master (sc_commodities): a commodity the agri-food shadow book
    reports that is not on it yet is added once, by name — never scored differently for being new."""
    cid = session.execute(text("SELECT commodity_id FROM sc_commodities WHERE lower(name) = lower(:n)"), {"n": name}).scalar()
    if cid:
        return str(cid)
    return str(session.execute(text("""
        INSERT INTO sc_commodities (name, eudr_covered) VALUES (:n, false)
        ON CONFLICT DO NOTHING RETURNING commodity_id
    """), {"n": name}).scalar() or session.execute(text("SELECT commodity_id FROM sc_commodities WHERE lower(name) = lower(:n)"), {"n": name}).scalar())


def build_shadow_book(session, *, regulator_org_id: str, subject_org_id: str, period_label: str, rows: list[dict],
                      raw: bytes, filename: Optional[str], mapping: dict, user_id: Optional[str], score: bool = True) -> dict:
    """Replace the regulator's shadow book for this subject with the mapped granular rows, resolve each row's
    region to a point (or leave it unlocated), and trigger scoring of the new cells. Returns the coverage report.
    The shadow book takes the subject's own vertical: the lens then rebuilds an insurer's template on the
    insurance engine and a bank's on the banking engine — the same engine the entity itself would run. Agriculture
    keeps its own book (sc_sourcing_plots, not the shared financial portfolio_entities engine — see
    services/portfolio_engine.py), so an agri-food authority's shadow rows land there instead, on the same
    own/supervisor_shadow split."""
    batch = str(uuid.uuid4())
    subj_type = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:s AS uuid)"), {"s": subject_org_id}).scalar()
    vertical = {"bank": "banking", "insurer": "insurance", "asset_manager": "assetmgmt", "reit": "realestate",
                "manufacturer": "agriculture"}.get(subj_type, "banking")
    ent_type = {"banking": "loan", "insurance": "property", "assetmgmt": "holding", "realestate": "property",
                "agriculture": "plot"}[vertical]
    shadow_table = "sc_sourcing_plots" if vertical == "agriculture" else "portfolio_entities"
    session.execute(text(f"""DELETE FROM {shadow_table} WHERE org_id = CAST(:r AS uuid) AND source = 'supervisor_shadow'
                            AND subject_org_id = CAST(:s AS uuid)"""), {"r": regulator_org_id, "s": subject_org_id})
    n_loc: dict[str, int] = {"nuts3": 0, "postcode→nuts3": 0, "point": 0, "unlocated": 0}
    cell_coords: dict[str, tuple[float, float]] = {}
    value_located = value_total = 0.0
    for r in rows:
        loc = _resolve_row_location(r)
        prec = loc["location_precision"] if loc else "unlocated"
        n_loc[prec] = n_loc.get(prec, 0) + 1
        val = float(r.get("outstanding_eur") or 0)
        value_total += val
        lat = lon = cell = None
        if loc:
            lat, lon = loc["lat"], loc["lon"]; cell = h3.latlng_to_cell(lat, lon, 8); cell_coords[cell] = (lat, lon); value_located += val
        eid = str(uuid.uuid4())
        nace = (r.get("nace_section") or "").strip().upper()
        if vertical == "agriculture":
            commodity_id = _get_or_create_commodity(session, nace or "Unclassified")
            session.execute(text("""
                INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude, h3_cell,
                                               country, region, annual_spend_eur, source, subject_org_id)
                VALUES (CAST(:id AS uuid), CAST(:o AS uuid), CAST(:cid AS uuid), :name, :lat, :lon, :cell,
                        :country, :region, :val, 'supervisor_shadow', CAST(:subj AS uuid))
            """), {"id": eid, "o": regulator_org_id, "cid": commodity_id,
                   "name": (r.get("counterparty_name") or r.get("instrument_id") or "plot")[:200],
                   "lat": lat, "lon": lon, "cell": cell, "country": (r.get("collateral_country") or "")[:2].upper() or None,
                   "region": (loc["name"] if loc else None), "val": val, "subj": subject_org_id})
        else:
            session.execute(text("""
                INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code, latitude, longitude,
                                                h3_cell, country, region, primary_value_eur, source, subject_org_id, location_precision, source_ref, external_ref)
                VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :vert, :name, :etype, :sector, :nace, :lat, :lon, :cell, :country, :region,
                        :val, 'supervisor_shadow', CAST(:subj AS uuid), :prec, :ref, :xref)
            """), {"id": eid, "o": regulator_org_id, "vert": vertical, "etype": ent_type, "name": (r.get("counterparty_name") or r.get("instrument_id") or "instrument")[:200],
                   "sector": nace[:100] or None, "nace": nace[:10] or None, "lat": lat, "lon": lon, "cell": cell,
                   "country": (r.get("collateral_country") or "")[:2].upper() or None,
                   "region": (loc["name"] if loc else None), "val": val, "subj": subject_org_id, "prec": prec, "ref": batch,
                   "xref": (str(r.get("instrument_id"))[:120] if r.get("instrument_id") else None)})
            if vertical == "banking":
              session.execute(text("""INSERT INTO ext_banking (entity_id, outstanding_loan_balance_eur, residual_maturity_years, data_source)
                                    VALUES (CAST(:id AS uuid), :bal, :rm, :src)"""),
                            {"id": eid, "bal": val, "rm": _residual_years(r.get("maturity_date")), "src": f"supervisor_shadow:{batch}"})
    session.flush()
    scoring = None
    if score and cell_coords:
        # Scoring a shadow book means raster and reanalysis reads for every new cell — never inside the request.
        # It runs on the jobs layer (worker, or a child process when the broker is away); the shadow status shows
        # n_scored climbing as cells land. The response says what was queued, not what was scored.
        try:
            from services.tasks.jobs import submit
            scoring = {"status": "queued", "n_cells": len(cell_coords), **submit("scoring.process_cells", cell_coords)}
        except Exception as e:
            scoring = {"status": "deferred", "error": str(e)[:200]}
    if score and cell_coords:
        # forward anchors (scenarios × horizons) take the same two paths a bank's own cells take — in the background
        from services.supervision.projection import schedule_projection
        schedule_projection(list(cell_coords))
    summary = {"batch": batch, "n_rows": len(rows), "located": n_loc, "coverage_value_pct": round(100.0 * value_located / value_total, 1) if value_total else None,
               "value_total_eur": round(value_total), "n_cells": len(cell_coords), "scoring": scoring,
               "projection": "scheduled" if (score and cell_coords) else "none"}
    save_submission(session, regulator_org_id=regulator_org_id, subject_org_id=subject_org_id, framework="granular", template="anacredit",
                    period_label=period_label, basis={}, cells=summary, raw=raw, filename=filename, mapping=mapping, user_id=user_id)
    return summary


def shadow_status(session, regulator_org_id: str, subject_org_id: str) -> dict:
    # the shadow book lives on portfolio_entities for the four financial verticals and on sc_sourcing_plots for
    # agriculture (its own book, same own/supervisor_shadow split) — a subject only ever has rows in one of the two.
    row = session.execute(text("""
        SELECT count(*) AS n, count(*) FILTER (WHERE latitude IS NOT NULL) AS n_located,
               COALESCE(SUM(value_eur), 0) AS value_eur,
               COALESCE(SUM(value_eur) FILTER (WHERE latitude IS NOT NULL), 0) AS value_located
        FROM (
            SELECT latitude, primary_value_eur AS value_eur FROM portfolio_entities
            WHERE org_id = CAST(:r AS uuid) AND source = 'supervisor_shadow' AND subject_org_id = CAST(:s AS uuid)
            UNION ALL
            SELECT latitude, annual_spend_eur AS value_eur FROM sc_sourcing_plots
            WHERE org_id = CAST(:r AS uuid) AND source = 'supervisor_shadow' AND subject_org_id = CAST(:s AS uuid)
        ) shadow
    """), {"r": regulator_org_id, "s": subject_org_id}).mappings().first()
    subs = session.execute(text("""
        SELECT s.framework, s.template, s.period_label, s.n_cells, s.source_file, s.created_at, s.basis, s.channel, u.full_name AS submitted_by
        FROM supervisor_submissions s LEFT JOIN users u ON u.user_id = s.created_by
        WHERE s.regulator_org_id = CAST(:r AS uuid) AND s.subject_org_id = CAST(:s AS uuid) ORDER BY s.created_at DESC
    """), {"r": regulator_org_id, "s": subject_org_id}).mappings().all()
    from services.supervision.projection import projection_coverage, shadow_cells
    return {"shadow_book": {"n_rows": int(row["n"]), "n_located": int(row["n_located"]), "value_eur": round(float(row["value_eur"])),
                            "coverage_value_pct": round(100.0 * float(row["value_located"]) / float(row["value_eur"]), 1) if row["value_eur"] else None,
                            "projection": projection_coverage(session, shadow_cells(session, regulator_org_id, subject_org_id))},
            "submissions": [dict(s) | {"created_at": s["created_at"].isoformat()} for s in subs],
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds")}
