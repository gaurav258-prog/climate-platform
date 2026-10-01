"""What a due diligence statement for one movement says, and what it rests on (E94) — gathered, not judged (the checks are
layer 4). Annex II of Regulation (EU) 2023/1115 as in force (point 4 deleted by 2025/2650):

  1  the operator's name, address and, for goods entering or leaving the market, its EORI number
  2  HS code, free-text description, trade name, the full scientific name where applicable, and the quantity
  3  the country of production and the geolocation of all plots of land (polygons over four hectares, cattle excepted —
     Art. 2(28); at least six decimal digits)
  5  the declaration text
  6  'Signed for and on behalf of: Date: Name and function: Signature:' — completed at attestation
and what the operator must hold (Art. 9(1)): production dates per plot, supplier and customer, the plots' readings, the
legality evidence, the risk assessment, the product's scope under Annex I and each country's risk (Art. 29).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

ANNEX_II_5 = ("By submitting this due diligence statement the operator confirms that due diligence in accordance with "
              "Regulation (EU) 2023/1115 was carried out and that no or only a negligible risk was found that the relevant "
              "products do not comply with Article 3, point (a) or (b), of that Regulation.")
ANNEX_II_6 = "Signed for and on behalf of: Date: Name and function: Signature:"
POLYGON_OVER_HA = 4                     # Art. 2(28): 'plots of land of more than four hectares … using polygons'
MIN_DECIMALS = 6                        # Art. 2(28): 'at least six decimal digits'


class StatementError(ValueError):
    pass


def _plots(session: Session, movement_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.plot_name, p.external_ref, p.country, p.latitude, p.longitude,
               p.plot_geometry IS NOT NULL AS has_polygon, CAST(p.plot_area_ha AS FLOAT) AS area_ha, p.coordinate_decimals,
               p.geocode_precision, p.supplier_id::text AS supplier_id, c.name AS commodity, l.production_from, l.production_to
        FROM eudr_movement_plot l JOIN sc_sourcing_plots p USING (plot_id) LEFT JOIN sc_commodities c USING (commodity_id)
        WHERE l.movement_id = CAST(:m AS uuid) ORDER BY p.plot_name"""), {"m": movement_id}).mappings().all()
    return [{**dict(r), "production_from": r["production_from"].isoformat(), "production_to": r["production_to"].isoformat()}
            for r in rows]


def countries_of(session: Session, org_id: str, movement_id: str, on: Optional[date] = None) -> dict[str, Optional[str]]:
    """Each country of production of the movement's plots → its risk under Art. 29 (Implementing Reg. (EU) 2025/1093)."""
    from services.reference.eudr_refdata import country_risk
    d = on or session.execute(text("SELECT planned_on FROM eudr_movement WHERE movement_id = CAST(:m AS uuid)"),
                              {"m": movement_id}).scalar()
    out: dict[str, Optional[str]] = {}
    for p in _plots(session, movement_id):
        if p["country"]:
            r = country_risk(p["country"], d)
            out[p["country"]] = r["risk"] if isinstance(r, dict) else r
    return out


def compute(session: Session, org_id: str, movement_id: str) -> dict:
    from services.eudr import reading as RD
    from services.eudr import records as REC
    from services.reference.eudr_refdata import scope
    m = session.execute(text("""
        SELECT m.*, m.movement_id::text AS id, s.name AS supplier_name, s.address AS supplier_address,
               s.contact_email AS supplier_email, c.name AS customer_name, c.address AS customer_address,
               c.contact_email AS customer_email, o.name AS org_name, o.legal_name AS org_legal_name
        FROM eudr_movement m LEFT JOIN sc_suppliers s USING (supplier_id) LEFT JOIN sc_customers c USING (customer_id)
        JOIN organizations o ON o.org_id = m.org_id
        WHERE m.movement_id = CAST(:m AS uuid) AND m.org_id = CAST(:o AS uuid)"""), {"m": movement_id, "o": org_id}).mappings().first()
    if m is None:
        raise StatementError("no such movement in this organisation")
    on = m["planned_on"]
    entity = str(m["reporting_entity_id"]) if m["reporting_entity_id"] else None
    status = REC.live_status(session, org_id, entity, on)
    plots = _plots(session, movement_id)
    readings = RD.current(session, [p["plot_id"] for p in plots]) if plots else {}
    countries = countries_of(session, org_id, movement_id, on)
    for p in plots:
        cattle = (p["commodity"] or "").lower() == "cattle"
        p["polygon_required"] = bool(not cattle and p["area_ha"] is not None and p["area_ha"] > POLYGON_OVER_HA)
        p["area_unknown"] = p["area_ha"] is None and not p["has_polygon"]
        p["reading"] = readings.get(p["plot_id"])
        p["country_risk"] = countries.get(p["country"])
    suppliers = sorted({p["supplier_id"] for p in plots if p["supplier_id"]} | ({str(m["supplier_id"])} if m["supplier_id"] else set()))
    evidence = REC.evidence_for(session, org_id, plot_ids=[p["plot_id"] for p in plots], supplier_ids=suppliers,
                                movement_id=movement_id, on=on)
    quantity = {k: (float(m[k]) if m[k] is not None and k != "items_count" else m[k])
                for k in ("net_mass_kg", "mass_deviation_pct", "supplementary_unit", "supplementary_qty", "volume_m3", "items_count")}
    return {
        "movement": {"movement_id": m["id"], "external_ref": m["external_ref"], "kind": m["kind"], "actor_role": m["actor_role"],
                     "planned_on": on.isoformat(), "customs_flow": m["customs_flow"],
                     "upstream_refs": list(m["upstream_refs"] or []), "reporting_entity_id": entity,
                     "scope_in": m["scope_in"], "scope_basis": m["scope_basis"]},
        "scope": scope(m["hs_code"], on),
        "operator_status": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in status.items()} if status else None,
        "annex_ii": {
            "1": {"name": m["org_legal_name"] or m["org_name"], "address": (status or {}).get("address"),
                  "eori": (status or {}).get("eori"), "country": (status or {}).get("country")},
            "2": {"hs_code": m["hs_code"], "description": m["description"], "trade_name": m["trade_name"],
                  "scientific_names": list(m["scientific_names"] or []), "quantity": quantity},
            "3": {"countries": sorted({p["country"] for p in plots if p["country"]}),
                  "plots": [{k: p[k] for k in ("plot_id", "plot_name", "external_ref", "country", "latitude", "longitude",
                                               "has_polygon", "area_ha", "coordinate_decimals")} for p in plots]},
            "5": ANNEX_II_5,
            "6": ANNEX_II_6,
        },
        "art9": {"supplier": {"name": m["supplier_name"], "address": m["supplier_address"], "email": m["supplier_email"]}
                 if m["supplier_id"] else None,
                 "customer": {"name": m["customer_name"], "address": m["customer_address"], "email": m["customer_email"]}
                 if m["customer_id"] else None,
                 "production": [{"plot_id": p["plot_id"], "from": p["production_from"], "to": p["production_to"]} for p in plots]},
        "plots": plots,
        "countries": countries,
        "legality_evidence": evidence,
        "risk_assessment": REC.live_assessment(session, movement_id),
    }
