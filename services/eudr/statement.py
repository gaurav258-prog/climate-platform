"""What a due diligence statement for one movement says, and what it rests on (E94) — gathered, not judged (the checks are
layer 4). Annex II of Regulation (EU) 2023/1115 in the version in force on the shipment's date (services/eudr/spec.py; its
wording is read from the captured spec, never typed here — E115): the operator (point 1), the product and its quantity
(2), the country of production and the geolocation of all plots (3; polygons over four hectares, cattle excepted, at
least six decimal digits — Art. 2(28)), in the first version a referenced statement (4, deleted by 2025/2650), the
confirmation (5) and the signature (6, completed at attestation); and what the operator must hold (Art. 9(1)): production dates per plot, supplier and customer, the plots' readings, the
legality evidence, the risk assessment, the product's scope under Annex I and each country's risk (Art. 29).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.eudr import spec as SP

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
               c.contact_email AS customer_email, o.name AS org_name, o.legal_name AS org_legal_name,
               (SELECT r.name FROM reporting_entities r WHERE r.entity_id = m.reporting_entity_id) AS entity_name
        FROM eudr_movement m LEFT JOIN sc_suppliers s USING (supplier_id) LEFT JOIN sc_customers c USING (customer_id)
        JOIN organizations o ON o.org_id = m.org_id
        WHERE m.movement_id = CAST(:m AS uuid) AND m.org_id = CAST(:o AS uuid)"""), {"m": movement_id, "o": org_id}).mappings().first()
    if m is None:
        raise StatementError("no such movement in this organisation")
    on = m["planned_on"]
    spec = SP.governing(on)
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
        "spec": SP.record(spec),
        "movement": {"movement_id": m["id"], "external_ref": m["external_ref"], "kind": m["kind"], "actor_role": m["actor_role"],
                     "planned_on": on.isoformat(), "customs_flow": m["customs_flow"],
                     "upstream_refs": list(m["upstream_refs"] or []), "reporting_entity_id": entity,
                     "scope_in": m["scope_in"], "scope_basis": m["scope_basis"]},
        "scope": scope(m["hs_code"], on),
        "operator_status": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in status.items()} if status else None,
        "annex_ii": {
            # the operator is the undertaking the shipment is booked to: its legal entity, else the organisation
            "1": {"name": m["entity_name"] or m["org_legal_name"] or m["org_name"], "address": (status or {}).get("address"),
                  "eori": (status or {}).get("eori"), "country": (status or {}).get("country")},
            "2": {"hs_code": m["hs_code"], "description": m["description"], "trade_name": m["trade_name"],
                  "scientific_names": list(m["scientific_names"] or []), "quantity": quantity},
            "3": {"countries": sorted({p["country"] for p in plots if p["country"]}),
                  "plots": [{k: p[k] for k in ("plot_id", "plot_name", "external_ref", "country", "latitude", "longitude",
                                               "has_polygon", "area_ha", "coordinate_decimals")} for p in plots]},
            **({"4": list(m["upstream_refs"] or [])} if SP.has_point(spec, "AII", "p4_referenced_statement") else {}),
            "5": SP.quoted(SP.point(spec, "AII", "p5_confirmation")["label"]),
            "6": SP.quoted(SP.point(spec, "AII", "p6_signature")["label"]),
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


# ───────────────────────────── the filed statement: what a reader sees ─────────────────────────────

def _qty(q: dict) -> str:
    parts = []
    if q.get("net_mass_kg") is not None:
        parts.append(f"{q['net_mass_kg']:,.3f} kg net mass" + (f" (± {q['mass_deviation_pct']} %)" if q.get("mass_deviation_pct") is not None else ""))
    if q.get("supplementary_unit"):
        parts.append(f"{q['supplementary_qty']:,} {q['supplementary_unit']}")
    if q.get("volume_m3") is not None:
        parts.append(f"{q['volume_m3']:,} m³")
    if q.get("items_count") is not None:
        parts.append(f"{q['items_count']:,} items")
    return "; ".join(parts) or "—"


def form(payload: dict) -> list[dict]:
    st = payload.get("statement") or {}
    if not st:
        return []
    a = st["annex_ii"]
    mv = st["movement"]
    return [{"section": "Due diligence statement (Annex II)", "rows": [
        {"label": "1 · Operator", "value": f"{a['1'].get('name')} · {a['1'].get('address') or '—'}"
                                           + (f" · EORI {a['1']['eori']}" if a['1'].get('eori') else "")},
        {"label": "2 · Product", "value": f"HS {a['2']['hs_code']} · {a['2']['description']}"
                                          + (f" · {a['2']['trade_name']}" if a['2'].get('trade_name') else "")
                                          + (f" · {', '.join(a['2']['scientific_names'])}" if a['2']['scientific_names'] else "")},
        {"label": "2 · Quantity", "value": _qty(a["2"]["quantity"])},
        {"label": "3 · Countries of production", "value": ", ".join(a["3"]["countries"]) or "—"},
        {"label": "3 · Plots", "value": str(len(a["3"]["plots"]))},
        {"label": "Shipment", "value": f"{mv['kind'].replace('_', ' ')} on {mv['planned_on']} · {mv.get('external_ref') or ''}"},
    ]}]


def sections(payload: dict) -> list[dict]:
    """The official-form tab: Annex II point by point as printed in the version the statement was prepared under (its
    wording from the spec), each with what the statement says."""
    import services.regspec as R
    st = payload.get("statement") or {}
    if not st:
        return []
    # a statement frozen before the spec was captured (E115) is shown under the version in force on its shipment's date —
    # the same rule the spec records
    spec = R.load(SP.FRAMEWORK, st["spec"]["version"]) if st.get("spec") else SP.governing(st["movement"]["planned_on"])
    a = st["annex_ii"]
    plots = a["3"]["plots"]
    said = {
        "p1_operator": ["; ".join(x for x in (a["1"].get("name"), a["1"].get("address"),
                                              a["1"].get("eori") and f"EORI {a['1']['eori']}") if x)],
        "p2_product": [f"HS {a['2']['hs_code']}",
                       " · ".join(x for x in (a["2"]["description"], a["2"].get("trade_name")) if x),
                       ", ".join(a["2"]["scientific_names"]) or "scientific name: —",
                       _qty(a["2"]["quantity"])],
        "p3_geolocation": [", ".join(a["3"]["countries"]) or "—",
                           *(f"{p['plot_name'] or p['plot_id']}: "
                             + ("polygon" if p["has_polygon"] else f"{p['latitude']}, {p['longitude']}")
                             + (f" · {p['area_ha']} ha" if p["area_ha"] is not None else "") for p in plots)],
        "p4_referenced_statement": [", ".join(a.get("4") or []) or "—"],
        "p5_confirmation": [a["5"]],
        "p6_signature": [a["6"]],
    }
    rows = []
    for i in SP.items(spec, "AII"):
        for k, v in enumerate(said[i["id"]]):
            rows.append({"type": "row", "cells": [{"text": f"{i['number']}. {i['label']}" if k == 0 else ""}, {"text": v}]})
    t = R.template(spec, "AII")
    return [{"title": f"{t['title']} — {t['ref']}", "key": "eudr_annex_ii", "columns": [t["code"], "Statement"],
             "rows": rows, "note": " ".join(t.get("capture_notes") or []) or None}]


def binding(spec: dict) -> dict:
    """How each point of Annex II is filled (services.regspec.coverage)."""
    src = {"p1_operator": "computed:operator_status", "p2_product": "computed:movement",
           "p3_geolocation": "computed:plots", "p4_referenced_statement": "computed:upstream_refs",
           "p6_signature": "input:attestation"}
    return {"AII": {"items": {i["id"]: src[i["id"]] for i in SP.items(spec, "AII") if i["kind"] != "text"}}}
