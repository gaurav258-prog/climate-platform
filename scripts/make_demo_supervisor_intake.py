"""Demo material for the Tier-2 lens: what a banking supervisor would hold about Meridian WITHOUT Meridian using
Tellumen — (1) an AnaCredit-style loan-level extract with the collateral REGION (NUTS-3 / postcode, no coordinates)
and (2) the Pillar 3 Template 5 the bank submitted (country × NACE section cells) — derived from the demo bank's
own book so the lens has something real to compare. Writes data/acceptance/demo_supervisor/*.csv.
Usage: PYTHONPATH=. .venv/bin/python scripts/make_demo_supervisor_intake.py
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

from core.db.session import get_session
from services.geo.org_assets import org_asset_points
from services.geo.regions import region_for
from services.governance.pillar3_templates import _section

MERIDIAN = "11111111-1111-4111-8111-111111111111"
IBERIA = "22222222-2222-4222-8222-222222222222"
STELLAR = "33333333-3333-4333-8333-333333333333"    # Stellar Logistics REIT (demo) — markets supervisor population
NORDKAP = "44444444-4444-4444-8444-444444444444"    # Nordkap Asset Management (demo) — markets supervisor population
ORANJE = "66666666-6666-4666-8666-666666666666"     # Oranje Foods NV (demo) — agri-food authority population
OUT = Path("data/acceptance/demo_supervisor")
BANK_BASIS = ("disorderly_2c", "2030")      # the basis the bank states in its narrative (≠ the supervisor's default)
_PROPERTY_TYPES = ("Office", "Retail", "Logistics", "Industrial", "Residential", "Warehousing", "Hotel")


def main(period: str = "FY2025", scale: float = 1.0, sensitivity_scale: float = 1.0) -> int:
    """period/scale: a second period (e.g. FY2024 at 0.92 × gross, 0.85 × sensitive) so trend views have two points."""
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    with get_session() as s:
        pts = org_asset_points(s, MERIDIAN, "baseline", "current")
        bank_view = {p["id"]: p for p in org_asset_points(s, MERIDIAN, *BANK_BASIS)}
    # (1) AnaCredit-style extract: collateral region from the asset's true location; ~8% carry only the country
    with (OUT / "meridian_anacredit_extract.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Instrument ID", "Debtor name", "NACE", "Outstanding nominal amount", "Final maturity", "Protection country", "Protection NUTS3"])
        for i, p in enumerate(pts):
            reg = region_for(p["lat"], p["lon"]) if p.get("lat") is not None else None
            nuts = reg["key"] if reg and reg["kind"] == "nuts3" and rng.random() > 0.08 else ""
            w.writerow([f"INS-{i+1:05d}", p["name"], p.get("nace_code") or "", f"{p['value_eur']:.2f}", f"20{rng.randint(27, 40)}-06-30", (p.get("country") or "ES"), nuts])
    # (2) the bank's submitted Template 5 under ITS basis: country × NACE section, sensitive = High/Very-high headline;
    #     the bank also 'forgot' one small country (scope) — a realistic gap for the lens to sort
    from core.types import score_to_bucket
    cells: dict = {}
    for p in pts:
        b = bank_view.get(p["id"], p)
        geo, sec = (p.get("country") or "ES"), _section(p.get("nace_code") or p.get("sector"))
        if geo == "HU":
            continue
        c = cells.setdefault((geo, sec), [0.0, 0.0])
        c[0] += p["value_eur"] * scale
        if b.get("score") is not None and score_to_bucket(float(b["score"])).value in ("H", "VH"):
            c[1] += p["value_eur"] * scale * sensitivity_scale
    name = "meridian_pillar3_template5_submitted.csv" if period == "FY2025" else f"meridian_pillar3_template5_submitted_{period}.csv"
    with (OUT / name).open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Geography", "Sector", "Gross carrying amount", "of which sensitive to physical risk"])
        for (g, sec), (gross, sens) in sorted(cells.items()):
            w.writerow([g, sec, f"{gross:.2f}", f"{sens:.2f}"])
    print(f"wrote {OUT}: {len(pts)} loan rows, {len(cells)} template cells; bank basis {BANK_BASIS}")
    return 0




def main_insurer(period: str = "FY2025", scale: float = 1.0, sensitivity_scale: float = 1.0) -> int:
    """The insurance supervisor's material about Iberia WITHOUT Iberia using Tellumen: (1) a statement-of-values
    extract with the risk REGION (NUTS-3 / postcode, no coordinates) and (2) the climate-exposure template Iberia
    submitted (country × occupancy cells, sum insured / of which in physical-risk zones) — from the demo insurer's
    own book so the lens has something real to compare."""
    from sqlalchemy import text

    from core.types import score_to_bucket
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(11)
    with get_session() as s:
        pts = org_asset_points(s, IBERIA, "baseline", "current")
        ins_view = {p["id"]: p for p in org_asset_points(s, IBERIA, *BANK_BASIS)}
        sectors = {r[0]: (r[1] or "Property") for r in s.execute(text("SELECT 'insurance:' || entity_id::text, sector FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)"), {"o": IBERIA}).fetchall()}
    with (OUT / "iberia_sov_extract.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Policy ID", "Insured name", "Occupancy", "Sum insured", "Policy expiry", "Risk country", "Risk NUTS3"])
        for i, p in enumerate(pts):
            reg = region_for(p["lat"], p["lon"]) if p.get("lat") is not None else None
            nuts = reg["key"] if reg and reg["kind"] == "nuts3" and rng.random() > 0.08 else ""
            w.writerow([f"POL-{i+1:05d}", p["name"], sectors.get(p["id"], "Property"), f"{p['value_eur']:.2f}", f"20{rng.randint(26, 28)}-12-31", (p.get("country") or "ES"), nuts])
    cells: dict = {}
    for p in pts:
        b = ins_view.get(p["id"], p)
        geo, sec = (p.get("country") or "ES"), sectors.get(p["id"], "Property")
        c = cells.setdefault((geo, sec), [0.0, 0.0])
        c[0] += p["value_eur"] * scale
        if b.get("score") is not None and score_to_bucket(float(b["score"])).value in ("H", "VH"):
            c[1] += p["value_eur"] * scale * sensitivity_scale
    name = "iberia_exposure_template_submitted.csv" if period == "FY2025" else f"iberia_exposure_template_submitted_{period}.csv"
    with (OUT / name).open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Geography", "Occupancy", "Sum insured", "of which in physical-risk zones"])
        for (g, sec), (gross, sens) in sorted(cells.items()):
            w.writerow([g, sec, f"{gross:.2f}", f"{sens:.2f}"])
    print(f"wrote {OUT}: {len(pts)} policy rows, {len(cells)} template cells; insurer basis {BANK_BASIS}")
    return 0


def _property_type(name: str) -> str:
    for t in _PROPERTY_TYPES:
        if t in name:
            return t
    return "Office"


def main_markets(period: str = "FY2025", scale: float = 1.0, sensitivity_scale: float = 1.0) -> int:
    """The markets supervisor's material about its two supervised entities WITHOUT either using Tellumen:
    (1) Nordkap Asset Management — a holdings-register extract (asset region, no coordinates) and the
    holdings_by_region climate-exposure template (country x issuer NACE section); (2) Stellar Logistics REIT —
    a property-register extract and the properties_by_region template (country x property type, sector_key
    'verbatim'). Both derived from each demo entity's own book so the lens has something real to compare."""
    from core.types import score_to_bucket
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(13)
    with get_session() as s:
        nk_pts = org_asset_points(s, NORDKAP, "baseline", "current")
        nk_view = {p["id"]: p for p in org_asset_points(s, NORDKAP, *BANK_BASIS)}
        st_pts = org_asset_points(s, STELLAR, "baseline", "current")
        st_view = {p["id"]: p for p in org_asset_points(s, STELLAR, *BANK_BASIS)}

    with (OUT / "nordkap_holdings_register_extract.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Position ID", "Issuer name", "Issuer sector (NACE)", "Position value", "Maturity / disposal date", "Asset country", "Asset NUTS3"])
        for i, p in enumerate(nk_pts):
            reg = region_for(p["lat"], p["lon"]) if p.get("lat") is not None else None
            nuts = reg["key"] if reg and reg["kind"] == "nuts3" and rng.random() > 0.08 else ""
            w.writerow([f"POS-{i+1:05d}", p["name"], p.get("nace_code") or "", f"{p['value_eur']:.2f}", f"20{rng.randint(27, 40)}-06-30", (p.get("country") or "ES"), nuts])
    cells: dict = {}
    for p in nk_pts:
        b = nk_view.get(p["id"], p)
        geo, sec = (p.get("country") or "ES"), _section(p.get("nace_code") or p.get("sector"))
        c = cells.setdefault((geo, sec), [0.0, 0.0])
        c[0] += p["value_eur"] * scale
        if b.get("score") is not None and score_to_bucket(float(b["score"])).value in ("H", "VH"):
            c[1] += p["value_eur"] * scale * sensitivity_scale
    name = "nordkap_holdings_template_submitted.csv" if period == "FY2025" else f"nordkap_holdings_template_submitted_{period}.csv"
    with (OUT / name).open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Geography", "Sector", "Position value", "of which in physical-risk zones"])
        for (g, sec), (gross, sens) in sorted(cells.items()):
            w.writerow([g, sec, f"{gross:.2f}", f"{sens:.2f}"])
    print(f"wrote {OUT}: {len(nk_pts)} holding rows, {len(cells)} template cells (Nordkap); basis {BANK_BASIS}")

    with (OUT / "stellar_property_register_extract.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Property ID", "Property name", "Property type", "Property value", "Lease expiry", "Property country", "Property NUTS3"])
        for i, p in enumerate(st_pts):
            reg = region_for(p["lat"], p["lon"]) if p.get("lat") is not None else None
            nuts = reg["key"] if reg and reg["kind"] == "nuts3" and rng.random() > 0.08 else ""
            w.writerow([f"PROP-{i+1:05d}", p["name"], _property_type(p["name"]), f"{p['value_eur']:.2f}", f"20{rng.randint(27, 32)}-12-31", (p.get("country") or "ES"), nuts])
    cells = {}
    for p in st_pts:
        b = st_view.get(p["id"], p)
        geo, sec = (p.get("country") or "ES"), _property_type(p["name"])
        c = cells.setdefault((geo, sec), [0.0, 0.0])
        c[0] += p["value_eur"] * scale
        if b.get("score") is not None and score_to_bucket(float(b["score"])).value in ("H", "VH"):
            c[1] += p["value_eur"] * scale * sensitivity_scale
    name = "stellar_properties_template_submitted.csv" if period == "FY2025" else f"stellar_properties_template_submitted_{period}.csv"
    with (OUT / name).open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Geography", "Property type", "Property value", "of which in physical-risk zones"])
        for (g, sec), (gross, sens) in sorted(cells.items()):
            w.writerow([g, sec, f"{gross:.2f}", f"{sens:.2f}"])
    print(f"wrote {OUT}: {len(st_pts)} property rows, {len(cells)} template cells (Stellar); basis {BANK_BASIS}")
    return 0


def main_agrifood(period: str = "FY2025", scale: float = 1.0, sensitivity_scale: float = 1.0) -> int:
    """The agri-food authority's material about Oranje Foods WITHOUT Oranje using Tellumen: (1) a sourcing-plot
    extract carrying the EUDR due-diligence geolocation (lat/lon) the way a real due-diligence statement does —
    ~8% of plots carry an origin country only, honestly unlocated like every other sector's edge case — and
    (2) the sourcing_by_origin template Oranje submitted (origin country x commodity, sector_key 'verbatim'),
    from Oranje's own sourcing-plot book so the lens has something real to compare."""
    from sqlalchemy import text

    from core.types import score_to_bucket
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(17)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT p.plot_id, p.plot_name, co.name AS commodity, p.annual_spend_eur, p.country, p.latitude, p.longitude
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
            WHERE p.org_id = CAST(:o AS uuid) ORDER BY p.plot_id
        """), {"o": ORANJE}).mappings().all()
        scored = {p["id"]: p for p in org_asset_points(s, ORANJE, "baseline", "current") if p["kind"] == "plot"}
        scored_view = {p["id"]: p for p in org_asset_points(s, ORANJE, *BANK_BASIS) if p["kind"] == "plot"}

    with (OUT / "oranje_sourcing_plot_extract.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Plot ID", "Supplier / plot name", "Commodity", "Annual sourcing spend", "Contract end", "Origin country", "Latitude", "Longitude"])
        for i, r in enumerate(rows):
            has_geo = rng.random() > 0.08
            lat = f"{r['latitude']:.6f}" if has_geo and r["latitude"] is not None else ""
            lon = f"{r['longitude']:.6f}" if has_geo and r["longitude"] is not None else ""
            w.writerow([f"PLOT-{i+1:05d}", r["plot_name"] or "", r["commodity"], f"{float(r['annual_spend_eur'] or 0):.2f}",
                       f"20{rng.randint(27, 32)}-12-31", r["country"] or "", lat, lon])

    cells: dict = {}
    for r in rows:
        key = f"plot:{r['plot_id']}"
        b = scored_view.get(key) or scored.get(key) or {}
        geo, sec = (r["country"] or "XX"), (r["commodity"] or "Commodity")
        c = cells.setdefault((geo, sec), [0.0, 0.0])
        val = float(r["annual_spend_eur"] or 0) * scale
        c[0] += val
        if b.get("score") is not None and score_to_bucket(float(b["score"])).value in ("H", "VH"):
            c[1] += val * sensitivity_scale
    name = "oranje_sourcing_template_submitted.csv" if period == "FY2025" else f"oranje_sourcing_template_submitted_{period}.csv"
    with (OUT / name).open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Origin country", "Commodity", "Annual sourcing spend", "of which in physical-risk zones"])
        for (g, sec), (gross, sens) in sorted(cells.items()):
            w.writerow([g, sec, f"{gross:.2f}", f"{sens:.2f}"])
    print(f"wrote {OUT}: {len(rows)} plot rows, {len(cells)} template cells (Oranje); basis {BANK_BASIS}")
    return 0


if __name__ == "__main__":
    import sys
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    fn = {"insurer": main_insurer, "markets": main_markets, "agrifood": main_agrifood}.get(args.get("sector"), main)
    raise SystemExit(fn(args.get("period", "FY2025"), float(args.get("scale", 1.0)), float(args.get("sensitivity_scale", 1.0))))
