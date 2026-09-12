"""Third-party physical exposure — the critical service providers, custodians, data centres and outsourcers an
organisation depends on, located and scored on the same engine as its own sites.

The register is the organisation's own (name, kind, service, criticality, contract). Location is resolved the way
every site is (exact coordinates or a real geocode with its precision), the H3 cell is scored on demand by the
existing scorers, and the exposure read is the standing score at that cell for every hazard — never a number
invented for a place the engine has not scored: an unscored cell says 'pending'. Kinds are configuration.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

KINDS = {"critical_service_provider": "Critical service provider", "cloud": "Cloud / hosting provider", "data_centre": "Data centre", "custodian": "Custodian / depositary",
         "outsourcer": "Outsourced function", "supplier": "Supplier", "other": "Other third party"}
CRITICALITY = ("critical", "important", "standard")


def add(session, *, org_id: str, name: str, kind: str, service: Optional[str], criticality: str, address: Optional[str], lat: Optional[float], lon: Optional[float],
        country: Optional[str], contract_ref: Optional[str], note: Optional[str], actor_user_id: str) -> dict:
    import h3

    from services.intelligence.company_sites import (
        H3_RESOLUTION,
        SiteLocationError,
        resolve_location,
    )
    from services.scoring.on_demand import schedule_scoring
    if kind not in KINDS:
        raise ValueError(f"Kind must be one of: {', '.join(KINDS)}.")
    if criticality not in CRITICALITY:
        raise ValueError(f"Criticality must be one of: {', '.join(CRITICALITY)}.")
    if not (name or "").strip():
        raise ValueError("Name the third party.")
    try:
        loc = resolve_location(address, lat, lon, session=session)
    except SiteLocationError as e:
        raise ValueError(str(e))
    cell = h3.latlng_to_cell(loc["lat"], loc["lon"], H3_RESOLUTION)
    tid = session.execute(text("""INSERT INTO third_party (org_id, name, kind, service, criticality, address, country, latitude, longitude, h3_cell, geocode_precision, contract_ref, note, created_by)
                                  VALUES (CAST(:o AS uuid), :n, :k, :s, :c, :a, :co, :la, :lo, :h, :gp, :cr, :nt, CAST(:u AS uuid)) RETURNING third_party_id::text"""),
                          {"o": org_id, "n": name.strip(), "k": kind, "s": (service or "").strip() or None, "c": criticality, "a": (address or "").strip() or None, "co": country,
                           "la": loc["lat"], "lo": loc["lon"], "h": cell, "gp": loc.get("precision"), "cr": (contract_ref or "").strip() or None, "nt": (note or "").strip() or None, "u": actor_user_id}).scalar()
    schedule_scoring({cell: (loc["lat"], loc["lon"])})
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="third_party.add", target_type="third_party", target_id=tid,
                detail={"name": name.strip(), "kind": kind, "criticality": criticality, "h3_cell": cell, "precision": loc.get("precision")})
    return {"third_party_id": tid, "h3_cell": cell, "lat": loc["lat"], "lon": loc["lon"], "precision": loc.get("precision")}


def end(session, *, org_id: str, third_party_id: str, actor_user_id: str) -> bool:
    row = session.execute(text("UPDATE third_party SET active = FALSE, ended_at = now() WHERE third_party_id = CAST(:t AS uuid) AND org_id = CAST(:o AS uuid) AND active RETURNING name"),
                          {"t": third_party_id, "o": org_id}).first()
    if not row:
        return False
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="third_party.end", target_type="third_party", target_id=third_party_id, detail={"name": row[0]})
    return True


def _scores(session, cells: list[str], scenario: str, horizon: str) -> dict[str, list[dict]]:
    if not cells:
        return {}
    rows = session.execute(text("""SELECT h3_cell, hazard_type, CAST(risk_score AS FLOAT) AS score, model_version FROM canonical_scores
                                   WHERE h3_cell = ANY(:c) AND scenario = :s AND time_horizon = :h AND valid_to IS NULL"""), {"c": cells, "s": scenario, "h": horizon}).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["h3_cell"], []).append({"hazard": r["hazard_type"], "score": r["score"], "model_version": r["model_version"]})
    return out


def view(session, org_id: str, scenario: str = "baseline", horizon: str = "current") -> dict:
    from core.types import score_to_bucket
    rows = session.execute(text("""SELECT t.third_party_id::text AS third_party_id, t.name, t.kind, t.service, t.criticality, t.address, t.country, t.latitude, t.longitude, t.h3_cell, t.geocode_precision,
                                          t.contract_ref, t.note, t.created_at, u.full_name AS created_by
                                   FROM third_party t LEFT JOIN users u ON u.user_id = t.created_by WHERE t.org_id = CAST(:o AS uuid) AND t.active ORDER BY
                                   CASE t.criticality WHEN 'critical' THEN 0 WHEN 'important' THEN 1 ELSE 2 END, t.name"""), {"o": org_id}).mappings().all()
    from core.hazard_relevance import is_headline_eligible, reason
    sc = _scores(session, sorted({r["h3_cell"] for r in rows}), scenario, horizon)
    out = []
    for r in rows:
        hz = sorted(sc.get(r["h3_cell"], []), key=lambda x: -x["score"])
        for h in hz:                       # a third party is a built asset: crop-scale and nowcast hazards never headline it
            h["relevant"] = is_headline_eligible(h["hazard"], "buildings", h.get("model_version"))
            if not h["relevant"]:
                h["why_not"] = reason(h["hazard"], "buildings", h.get("model_version"))
        relevant = [h for h in hz if h["relevant"]]
        top = relevant[0] if relevant else None
        out.append(dict(r) | {"created_at": r["created_at"].isoformat(), "kind_label": KINDS.get(r["kind"], r["kind"]), "hazards": hz, "n_hazards_scored": len(hz),
                              "max_score": top["score"] if top else None, "worst_hazard": top["hazard"] if top else None, "bucket": score_to_bucket(top["score"]) if top else None,
                              "scored": bool(hz), "n_not_applicable": sum(1 for h in hz if not h["relevant"])})
    high = [x for x in out if x["max_score"] is not None and x["max_score"] >= 60]
    return {"third_parties": out, "kinds": KINDS, "criticality": list(CRITICALITY), "scenario": scenario, "horizon": horizon,
            "summary": {"n": len(out), "critical": sum(1 for x in out if x["criticality"] == "critical"), "scored": sum(1 for x in out if x["scored"]), "pending": sum(1 for x in out if not x["scored"]),
                        "high": len(high), "critical_high": sum(1 for x in high if x["criticality"] == "critical")},
            "note": "Each third party is located like your own sites and read at the same engine score. A newly added location scores in the background; until then it is shown as pending, never guessed. Hazards whose scale does not apply to a built asset (crop-frost, soil water, land degradation) are listed but never headline."}


def register_csv(v: dict) -> bytes:
    import csv
    import io
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Name", "Kind", "Service", "Criticality", "Address", "Country", "Latitude", "Longitude", "H3 cell", "Location precision", "Contract", "Worst hazard", "Max score", "Bucket", "Hazards scored", "Added", "By"])
    for t in v["third_parties"]:
        w.writerow([t["name"], t["kind_label"], t["service"] or "", t["criticality"], t["address"] or "", t["country"] or "", t["latitude"], t["longitude"], t["h3_cell"], t["geocode_precision"] or "", t["contract_ref"] or "",
                    t["worst_hazard"] or "pending", t["max_score"] if t["max_score"] is not None else "", t["bucket"] or "", t["n_hazards_scored"], t["created_at"][:10], t["created_by"] or ""])
    return buf.getvalue().encode("utf-8")
