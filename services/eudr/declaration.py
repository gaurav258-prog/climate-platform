"""The one-time simplified declaration of a micro or small primary operator (E115) — Regulation (EU) 2023/1115 as amended
by 2025/2650, Article 4a and Annex III (wording read from the captured spec, services/eudr/spec.py).

  who      a 'micro or small primary operator' (Art. 2(15a)): a natural person or micro / small undertaking, established
           in a low-risk country (Art. 29), placing products it itself grew, harvested, obtained from or raised on plots —
           the undertaking states the last part (its status, primary_own_produce); the platform checks the rest
  what     Annex III: 1 the operator's name, address and, entering or leaving the market, EORI; 2 each product's HS code,
           description with trade name, and one-off estimated annual quantity; 3 the country of production and the
           geolocation of all plots or their postal address (Art. 4a(5)); 4 the confirmation (printed wording)
  where    Art. 4a(4): where all of it is held in a Union or Member State system the undertaking names, no declaration need
           be submitted — the Member State makes it available; the declaration identifier still comes before any placing

Gathered here, judged in checks(); the declaration is a filing (services/eudr/declaration_filing.py).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.eudr import spec as SP
from services.eudr.statement import MIN_DECIMALS, POLYGON_OVER_HA

SIZE_CLASSES = ("micro", "small")                 # Art. 2(15a): 'a micro-undertaking or small undertaking'


class DeclarationError(ValueError):
    pass


def _f(rule: str, severity: str, passed: bool, message: str, ref: Optional[str] = None) -> dict:
    return {"rule": rule, "category": "eudr", "severity": severity, "passed": bool(passed), "message": message, "ref": ref}


# ── the products it declares (Annex III point 2) ──

def add_line(session: Session, org_id: str, user_id: str, *, entity_id: Optional[str], hs_code: str, description: str,
             customs_flow: bool, trade_name: Optional[str] = None, est_net_mass_kg: Optional[float] = None,
             mass_deviation_pct: Optional[float] = None, supplementary_unit: Optional[str] = None,
             supplementary_qty: Optional[float] = None, volume_m3: Optional[float] = None,
             items_count: Optional[int] = None, scope_in: Optional[bool] = None, scope_basis: Optional[str] = None) -> str:
    from services.reference.eudr_refdata import scope
    code = "".join(ch for ch in hs_code if ch.isdigit())
    sc = scope(code, date.today())
    if sc["in_scope"] is False:
        raise DeclarationError(f"HS {code} is not a relevant product under Annex I today: {sc.get('why')}")
    if sc["in_scope"] is True and scope_in is not None:
        raise DeclarationError("Annex I decides this product's scope — no statement of scope is taken")
    if (scope_in is None) != (not (scope_basis or "").strip()):
        raise DeclarationError("a statement of scope needs both whether it is in scope and why")
    if sc["in_scope"] is None and scope_in is None:
        raise DeclarationError(f"Annex I leaves this product's scope open ({sc.get('why')}) — state whether it is in scope, and why")
    if est_net_mass_kg is None and volume_m3 is None and items_count is None:
        raise DeclarationError("state the one-off estimated annual quantity: net mass, volume or number of items (Annex III point 2)")
    return str(session.execute(text("""
        INSERT INTO eudr_declaration_line (org_id, reporting_entity_id, hs_code, description, trade_name, customs_flow,
                                           est_net_mass_kg, mass_deviation_pct, supplementary_unit, supplementary_qty,
                                           volume_m3, items_count, scope_in, scope_basis, recorded_by)
        VALUES (CAST(:o AS uuid), CAST(:e AS uuid), :hs, :d, :tn, :cf, :m, :dev, :su, :sq, :v, :n, :si, :sb, CAST(:u AS uuid))
        RETURNING line_id"""), {"o": org_id, "e": entity_id, "hs": code, "d": description.strip(), "tn": trade_name,
                                "cf": customs_flow, "m": est_net_mass_kg, "dev": mass_deviation_pct, "su": supplementary_unit,
                                "sq": supplementary_qty, "v": volume_m3, "n": items_count, "si": scope_in,
                                "sb": (scope_basis or "").strip() or None, "u": user_id}).scalar())


def remove_line(session: Session, org_id: str, line_id: str) -> None:
    n = session.execute(text("""UPDATE eudr_declaration_line SET removed_at = now() WHERE line_id = CAST(:l AS uuid)
                                AND org_id = CAST(:o AS uuid) AND removed_at IS NULL"""), {"l": line_id, "o": org_id}).rowcount
    if not n:
        raise DeclarationError("no such product line")


def lines(session: Session, org_id: str, entity_id: Optional[str]) -> list[dict]:
    rows = session.execute(text("""
        SELECT line_id::text AS line_id, hs_code, description, trade_name, customs_flow,
               CAST(est_net_mass_kg AS FLOAT) AS est_net_mass_kg, CAST(mass_deviation_pct AS FLOAT) AS mass_deviation_pct,
               supplementary_unit, CAST(supplementary_qty AS FLOAT) AS supplementary_qty,
               CAST(volume_m3 AS FLOAT) AS volume_m3, items_count, scope_in, scope_basis
        FROM eudr_declaration_line WHERE org_id = CAST(:o AS uuid) AND removed_at IS NULL
          AND reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) ORDER BY seq"""),
        {"o": org_id, "e": entity_id}).mappings().all()
    return [dict(r) for r in rows]


# ── the declaration as it stands ──

def _plots(session: Session, org_id: str, entity_id: Optional[str], on: date) -> list[dict]:
    """Every plot of land of a relevant commodity the undertaking holds on the date (Annex III point 3: 'all plots of land')."""
    rows = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.plot_name, p.external_ref, p.country, p.latitude, p.longitude,
               p.plot_geometry IS NOT NULL AS has_polygon, CAST(p.plot_area_ha AS FLOAT) AS area_ha, p.coordinate_decimals,
               p.postal_address, c.name AS commodity
        FROM sc_sourcing_plots p JOIN sc_commodities c USING (commodity_id)
        WHERE p.org_id = CAST(:o AS uuid) AND c.eudr_covered AND (CAST(:e AS uuid) IS NULL OR p.entity_id = CAST(:e AS uuid))
          AND (p.held_from IS NULL OR p.held_from <= :d) AND (p.held_until IS NULL OR p.held_until > :d)
        ORDER BY p.plot_name"""), {"o": org_id, "e": entity_id, "d": on}).mappings().all()
    out = []
    for r in rows:
        p = dict(r)
        cattle = (p["commodity"] or "").lower() == "cattle"
        p["polygon_required"] = bool(not cattle and p["area_ha"] is not None and p["area_ha"] > POLYGON_OVER_HA)
        out.append(p)
    return out


def compute(session: Session, org_id: str, entity_id: Optional[str], on: Optional[date] = None) -> dict:
    from services.eudr import records as REC
    from services.reference.eudr_refdata import country_risk
    on = on or date.today()
    spec = SP.governing(on)
    if not SP.has(spec, "AIII"):
        raise DeclarationError(f"the version in force on {on} has no simplified declaration (Annex III)")
    status = REC.live_status(session, org_id, entity_id, on)
    # the declaring operator is the undertaking: the legal entity, else the organisation
    org = session.execute(text("""SELECT COALESCE((SELECT r.name FROM reporting_entities r WHERE r.entity_id = CAST(:e AS uuid)
                                                    AND r.org_id = o.org_id), o.legal_name, o.name) AS name
                                  FROM organizations o WHERE o.org_id = CAST(:o AS uuid)"""),
                          {"o": org_id, "e": entity_id}).mappings().first()
    from services.reference.eudr_refdata import scope
    ls, plots = lines(session, org_id, entity_id), _plots(session, org_id, entity_id, on)
    for x in ls:                                   # Annex I as in force on the declaration's date, not when the line was added
        sc = scope(x["hs_code"], on)
        x["annex_scope"] = {"in_scope": sc["in_scope"], "why": sc.get("why"), "version": sc.get("version")}
    est_risk = country_risk(status["country"], on) if status and status.get("country") else None
    return {
        "on": on.isoformat(), "entity_id": entity_id, "spec": SP.record(spec),
        "operator_status": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in status.items()} if status else None,
        "established_risk": est_risk["risk"] if isinstance(est_risk, dict) else est_risk,
        "annex_iii": {
            "1": {"name": org["name"], "address": (status or {}).get("address"),
                  "eori": (status or {}).get("eori"), "country": (status or {}).get("country")},
            "2": ls,
            "3": {"countries": sorted({p["country"] for p in plots if p["country"]}),
                  "plots": [{k: p[k] for k in ("plot_id", "plot_name", "external_ref", "country", "latitude", "longitude",
                                               "has_polygon", "area_ha", "coordinate_decimals", "postal_address")} for p in plots]},
            "4": SP.quoted(SP.point(spec, "AIII", "p4_confirmation")["label"]),
        },
        "plots": plots,
    }


def checks(st: dict) -> list[dict]:
    """What the declaration must satisfy before it can be prepared, each with its article."""
    out: list[dict] = []
    status, a3 = st.get("operator_status"), st["annex_iii"]
    # who may make it — Art. 2(15a)
    if status is None:
        out.append(_f("annex_iii_1", "blocking", False, "state the undertaking's EUDR status (size, country, address)", "Annex III point 1"))
    else:
        if status["size_class"] not in SIZE_CLASSES:
            out.append(_f("filer", "blocking", False, f"a {status['size_class']} undertaking is not a micro or small primary "
                          "operator — it submits due diligence statements", "Art. 2(15a), 4a"))
        if st["established_risk"] != "low":
            out.append(_f("filer_country", "blocking", False, f"established in {status['country']}, classified "
                          f"{st['established_risk'] or 'not classified'} — the simplified regime is for operators established "
                          "in a low-risk country", "Art. 2(15a), 29"))
        own = status.get("primary_own_produce")
        if own is not True:
            out.append(_f("own_produce", "blocking", False, "not stated that it places products it itself grew, harvested, "
                          "obtained from or raised on its plots" if own is None else "stated that it does not place its own "
                          "produce — it is not a primary operator", "Art. 2(15a)"))
        if status.get("other_system"):
            out.append(_f("other_system", "info", True, f"all Annex III information is held in {status['other_system']}: "
                          "no declaration need be submitted — the Member State makes it available; place products only "
                          "after the declaration identifier is assigned", "Art. 4a(4)"))
        if not a3["1"].get("address"):
            out.append(_f("annex_iii_1", "blocking", False, "the operator's address is not stated", "Annex III point 1"))
        if any(x["customs_flow"] for x in a3["2"]) and not a3["1"].get("eori"):
            out.append(_f("annex_iii_1_eori", "blocking", False, "products entering or leaving the market: the EORI number "
                          "is required", "Annex III point 1"))
    # the products — Annex III point 2
    if not a3["2"]:
        out.append(_f("annex_iii_2", "blocking", False, "no relevant product is declared", "Annex III point 2"))
    for x in a3["2"]:
        name = f"HS {x['hs_code']}"
        sc = x["annex_scope"]["in_scope"]
        if sc is False:
            out.append(_f(f"scope:{x['line_id']}", "blocking", False, f"{name} is not a relevant product on {st['on']}: "
                          f"{x['annex_scope']['why']}", "Art. 2(2), Annex I"))
        elif sc is None and x["scope_in"] is None:
            out.append(_f(f"scope:{x['line_id']}", "blocking", False, f"{name}: Annex I leaves its scope open "
                          f"({x['annex_scope']['why']}) — state whether it is in scope, and why", "Annex I"))
        elif sc is None and x["scope_in"] is False:
            out.append(_f(f"scope:{x['line_id']}", "blocking", False, f"{name} stated out of scope: {x['scope_basis']}", "Annex I"))
        if x["customs_flow"] and x["est_net_mass_kg"] is None:
            out.append(_f(f"quantity:{x['line_id']}", "blocking", False, f"{name}: entering or leaving the market, the estimated "
                          "quantity is expressed in kilograms of net mass", "Annex III point 2"))
        if not x["customs_flow"] and x["est_net_mass_kg"] is not None and x["mass_deviation_pct"] is None:
            out.append(_f(f"quantity:{x['line_id']}", "blocking", False, f"{name}: net mass is stated 'specifying a percentage "
                          "estimate or deviation'", "Annex III point 2"))
    # where it is produced — Annex III point 3, Art. 4a(5), Art. 2(28)
    plots = st["plots"]
    if not plots:
        out.append(_f("annex_iii_3", "blocking", False, "no plot of land of a relevant commodity is held", "Annex III point 3"))
    for p in plots:
        name = p["plot_name"] or p["plot_id"]
        if not p["country"]:
            out.append(_f(f"country:{p['plot_id']}", "blocking", False, f"{name}: country of production not stated", "Annex III point 3"))
        geo_ok = (p["coordinate_decimals"] is not None and p["coordinate_decimals"] >= MIN_DECIMALS
                  and not (p["polygon_required"] and not p["has_polygon"]))
        if not geo_ok and not (p.get("postal_address") or "").strip():
            out.append(_f(f"location:{p['plot_id']}", "blocking", False, f"{name}: neither a geolocation as Art. 2(28) asks "
                          f"(at least {MIN_DECIMALS} decimals; a polygon over {POLYGON_OVER_HA} ha) nor its postal address",
                          "Annex III point 3; Art. 4a(5)"))
        if status and p["country"] and p["country"] != status.get("country"):
            out.append(_f(f"plot_country:{p['plot_id']}", "warning", False, f"{name} is in {p['country']}, the undertaking is "
                          f"established in {status.get('country')} — the definition speaks of the operator's own production "
                          "and of establishments 'located in that country'", "Art. 2(15a)"))
    if not any(not f["passed"] and f["severity"] == "blocking" for f in out):
        out.append(_f("ready", "info", True, "every blocking check passes"))
    return out


def form(payload: dict) -> list[dict]:
    st = payload.get("declaration") or {}
    if not st:
        return []
    a = st["annex_iii"]
    return [{"section": "Simplified declaration (Annex III)", "rows": [
        {"label": "Point 1", "value": " · ".join(v for v in (a["1"].get("name"), a["1"].get("address"),
                                                             a["1"].get("eori") and f"EORI {a['1']['eori']}") if v)},
        {"label": "Point 2", "value": f"{len(a['2'])} product(s): " + ", ".join(f"HS {x['hs_code']}" for x in a["2"])},
        {"label": "Point 3", "value": f"{len(a['3']['plots'])} plot(s) · " + (", ".join(a["3"]["countries"]) or "—")},
        {"label": "Declaration date", "value": st["on"]},
    ]}]


def sections(payload: dict) -> list[dict]:
    """The official-form tab: Annex III point by point as printed, each with what the declaration says."""
    import services.regspec as R
    st = payload.get("declaration") or {}
    if not st:
        return []
    spec = R.load(SP.FRAMEWORK, st["spec"]["version"])
    a = st["annex_iii"]

    def qty(x: dict) -> str:
        parts = []
        if x["est_net_mass_kg"] is not None:
            parts.append(f"{x['est_net_mass_kg']:,.0f} kg net mass"
                         + (f" ± {x['mass_deviation_pct']:g} %" if x["mass_deviation_pct"] is not None else ""))
        if x["supplementary_qty"] is not None:
            parts.append(f"{x['supplementary_qty']:g} {x['supplementary_unit'] or ''}".strip())
        if x["volume_m3"] is not None:
            parts.append(f"{x['volume_m3']:g} m³")
        if x["items_count"] is not None:
            parts.append(f"{x['items_count']} items")
        return " · ".join(parts)

    said = {
        "p1_operator": ["; ".join(v for v in (a["1"].get("name"), a["1"].get("address"),
                                              a["1"].get("eori") and f"EORI {a['1']['eori']}") if v)],
        "p2_product_estimate": [f"HS {x['hs_code']} · " + " · ".join(v for v in (x["description"], x.get("trade_name")) if v)
                                + f" · {qty(x)} a year (estimated)" for x in a["2"]] or ["—"],
        "p3_location": [", ".join(a["3"]["countries"]) or "—",
                        *(f"{p['plot_name'] or p['plot_id']}: "
                          + (("polygon" if p["has_polygon"] else f"{p['latitude']}, {p['longitude']}")
                             if p["coordinate_decimals"] is not None and p["coordinate_decimals"] >= MIN_DECIMALS
                             else f"postal address: {p['postal_address']}") for p in a["3"]["plots"])],
        "p4_confirmation": [a["4"]],
    }
    rows = []
    for i in SP.items(spec, "AIII"):
        for k, v in enumerate(said[i["id"]]):
            rows.append({"type": "row", "cells": [{"text": f"{i['number']}. {i['label']}" if k == 0 else ""}, {"text": v}]})
    t = R.template(spec, "AIII")
    return [{"title": f"{t['title']} — {t['ref']}", "key": "eudr_annex_iii", "columns": [t["code"], "Declaration"],
             "rows": rows, "note": " ".join(t.get("capture_notes") or []) or None}]


def binding(spec: dict) -> dict:
    """How each point of Annex III is filled (services.regspec.coverage)."""
    src = {"p1_operator": "computed:operator_status", "p2_product_estimate": "input:declaration_lines",
           "p3_location": "computed:plots"}
    return {"AIII": {"items": {i["id"]: src[i["id"]] for i in SP.items(spec, "AIII") if i["kind"] != "text"}}}
