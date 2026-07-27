"""EUDR Due Diligence Statement assembler (Tier 1 — build it ourselves).

Assembles a submission-ready DDS from the book we already hold: operator identity, the
EUDR-covered commodities (HS code + country of production), the geolocation of every plot, and
OUR computed deforestation-free determination + evidence per plot. The operator (or their broker)
files the exported statement in the EU TRACES / Information System and enters the reference number
back — Tier 2 will submit it over the TRACES API directly.

Honesty is the whole point of the gate: a DDS may only be FILED for plots we determined
`deforestation_free` with sufficient geolocation. Any covered plot that is non_compliant,
geolocation_incomplete, insufficient, or not-yet-determined is a BLOCKER, listed explicitly —
never quietly filed. Fields the operator must still complete in TRACES (net-mass quantity, EORI/
address if missing, the signed declaration) are surfaced as `operator_completes`, not faked.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.intelligence.eudr import DEFORESTATION_FREE

# The operator's due-diligence declaration (EUDR Art. 4/8) — the legal attestation they sign.
DD_STATEMENT = (
    "The operator confirms that due diligence was carried out in accordance with Regulation (EU) "
    "2023/1115 and that only a negligible risk exists that the relevant products do not comply — "
    "i.e. they are deforestation-free (produced on land not subject to deforestation after "
    "31 December 2020) and produced in accordance with the relevant legislation of the country of "
    "production. This statement is supported by geolocation of all plots and satellite "
    "verification of forest-cover change."
)


def assemble_dds(session, org_id: str) -> dict:
    """Build the DDS payload + readiness for an org's EUDR-covered book. Pure read; no writes."""
    org = session.execute(text(
        "SELECT legal_name, name, eori, operator_address, country FROM organizations WHERE org_id=:o"
    ), {"o": org_id}).mappings().first()
    operator = {
        "name": (org["legal_name"] or org["name"]) if org else None,
        "eori": org["eori"] if org else None,
        "address": org["operator_address"] if org else None,
        "country": org["country"] if org else None,
    }

    rows = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.plot_name, p.country, p.plot_geometry,
               CAST(p.latitude AS FLOAT) AS lat, CAST(p.longitude AS FLOAT) AS lon,
               CAST(p.plot_area_ha AS FLOAT) AS area_ha,
               p.eudr_determination, p.eudr_first_loss_year, p.eudr_forest_source,
               co.name AS commodity, co.hs_code
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o AND co.eudr_covered = TRUE
        ORDER BY co.name, p.plot_name
    """), {"o": org_id}).mappings().all()

    items: dict = {}     # commodity -> item
    blockers: list = []
    for r in rows:
        geoloc = r["plot_geometry"] or {"type": "Point", "coordinates": [r["lon"], r["lat"]]}
        plot_rec = {
            "plot_id": r["plot_id"], "plot_name": r["plot_name"], "country": r["country"],
            "area_ha": r["area_ha"], "geolocation": geoloc,
            "determination": r["eudr_determination"], "forest_source": r["eudr_forest_source"],
        }
        if r["eudr_determination"] != DEFORESTATION_FREE:
            blockers.append({
                "plot_id": r["plot_id"], "plot": r["plot_name"], "commodity": r["commodity"],
                "determination": r["eudr_determination"] or "not_determined",
                "reason": _blocker_reason(r["eudr_determination"], r["eudr_first_loss_year"]),
            })
            continue   # only deforestation-free plots enter the fileable statement
        it = items.setdefault(r["commodity"], {
            "commodity": r["commodity"], "hs_code": r["hs_code"],
            "countries_of_production": set(), "plots": [], "plot_count": 0})
        it["plots"].append(plot_rec)
        it["plot_count"] += 1
        if r["country"]:
            it["countries_of_production"].add(r["country"])

    for it in items.values():
        it["countries_of_production"] = sorted(it["countries_of_production"])
        # We do not hold net-mass tonnage per plot — the operator supplies quantity at filing.
        it["quantity_net_mass_kg"] = None

    missing_operator = [k for k in ("name", "eori", "address") if not operator.get(k)]
    operator_completes = []
    if missing_operator:
        operator_completes.append(f"operator identity: {', '.join(missing_operator)}")
    operator_completes.append("net-mass quantity (kg) per commodity")
    operator_completes.append("signature of the due-diligence declaration")

    covered = len(rows)
    fileable_plots = sum(it["plot_count"] for it in items.values())
    ready = len(blockers) == 0 and not missing_operator and fileable_plots > 0

    return {
        "operator": operator,
        "items": list(items.values()),
        "statement": DD_STATEMENT,
        "covered_plots": covered,
        "fileable_plots": fileable_plots,
        "blockers": blockers,
        "operator_completes": operator_completes,
        "ready": ready,
        "reason": _readiness_reason(ready, blockers, missing_operator, fileable_plots),
    }


def _blocker_reason(det: Optional[str], first_loss_year: Optional[int]) -> str:
    if det == "non_compliant":
        return f"forest loss detected after the cutoff ({first_loss_year}) — cannot be filed as deforestation-free"
    if det == "geolocation_incomplete":
        return ">4 ha plot needs a polygon boundary before it can be filed"
    if det == "insufficient":
        return "forest data could not be read — re-run the determination"
    return "not yet determined — run the deforestation determination first"


def _readiness_reason(ready, blockers, missing_operator, fileable) -> str:
    if ready:
        return "All covered plots are deforestation-free and operator identity is complete — ready to file."
    parts = []
    if fileable == 0:
        parts.append("no fileable (deforestation-free) plots yet")
    if blockers:
        parts.append(f"{len(blockers)} plot(s) blocked")
    if missing_operator:
        parts.append(f"operator identity incomplete ({', '.join(missing_operator)})")
    return "Not ready: " + "; ".join(parts) + "."
