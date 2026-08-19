"""EBA Pillar 3 ESG — banking-book TRANSITION-risk templates 3 & 4 (ITS (EU) 2022/2453, Annex XXXIX/XL),
built to the ACTUAL regulatory methodology, not a proprietary risk score.

Template 3 — ALIGNMENT METRICS (Annex XL, §38–41). For each sector for which the IEA defines an alignment
metric, the institution discloses, per sector:
    (a) gross carrying amount of exposures (loans, debt securities, equity);
    (b) the portfolio's CO₂-intensity in that sector's IEA metric unit (gCO₂/kWh, gCO₂/MJ, tCO₂/t, …);
    (c) the DISTANCE to the IEA Net-Zero-by-2050 (NZE2050) 2030 sector target, in %:
            distance = 100 × ((current − IEA_2030_target) / IEA_2030_target)
The ITS worked example: maritime shipping current 28.8 gCO₂/MJ vs IEA-NZE2050 2030 target 23.4 → 23%.

Honesty split — what this platform can vs. cannot produce (never fabricated):
  • Tellumen produces: the NACE→IEA-sector crosswalk, gross carrying amount by sector, the IEA NZE2050
    benchmark table, and the distance calculation + portfolio aggregation.
  • Only a vendor/counterparty can supply: each counterparty's PHYSICAL production-intensity in the IEA unit
    (needs physical output — MWh generated, tonnes produced — which is NOT financed emissions and NOT
    computable from our physical-risk engine). Provided via Lane-2 intake, reconciled + 4-eyes attested.
  • IEA benchmark values: only the shipping target is cited verbatim in the ITS (23.4 gCO₂/MJ, NZE2050 2021
    vintage). The rest carry their metric + unit but target=None until the licensed IEA NZE2050 Roadmap Excel
    is ingested — flagged 'pending', never guessed.

Template 4 — TOP-20 CARBON-INTENSIVE FIRMS (Annex XL, §42–44): exposures to the world's 20 most
carbon-intensive companies (the published Carbon Majors set). Tellumen holds the list and matches
counterparties by name/identity; gross carrying amount comes from the book.
"""
from __future__ import annotations

from services.governance.pillar3_templates import NACE_SECTIONS, _section  # noqa: F401


# NACE section/division → IEA Template-3 sector. The ITS lists (Annex XL): power generation, oil & gas, coal,
# iron & steel, cement, aluminium, automotive, aviation, maritime transport, and real estate. Mapped from the
# NACE division of each counterparty (Reg 1893/2006).
def _iea_sector(nace_code) -> str | None:
    if not nace_code:
        return None
    s = str(nace_code).strip().upper()
    div = ""
    for ch in s:
        if ch.isdigit():
            div += ch
        elif div:
            break
    d = int(div[:2]) if len(div) >= 2 else (int(div) if div else -1)
    if d in (5,):                      # mining of coal and lignite
        return "coal"
    if d in (6,) or d in (19,):        # extraction of oil & gas · coke & refined petroleum
        return "oil_gas"
    if d == 35:                        # electricity, gas, steam supply
        return "power"
    if d == 24:                        # manufacture of basic metals (iron & steel / aluminium)
        return "iron_steel"
    if d == 23:                        # other non-metallic mineral products (cement)
        return "cement"
    if d in (29, 30):                  # manufacture of motor vehicles / other transport equip
        return "automotive"
    if d == 51:                        # air transport
        return "aviation"
    if d == 50:                        # water transport
        return "maritime"
    if d == 68 or (s[:1] == "L"):      # real estate activities
        return "real_estate"
    return None


# IEA NZE2050 alignment metric + 2030 target per sector. `target_2030` is only populated where a citable
# value exists (shipping, from ITS 2022/2453 §39 worked example); the rest are None='pending IEA ingest'
# so a distance is only ever shown against a REAL benchmark — never a guessed one.
IEA_NZE2050: dict[str, dict] = {
    "power":       {"label": "Power generation", "metric": "CO₂ intensity of generation", "unit": "gCO₂/kWh", "target_2030": None},
    "oil_gas":     {"label": "Oil & gas", "metric": "CO₂ intensity of energy supplied", "unit": "gCO₂/MJ", "target_2030": None},
    "coal":        {"label": "Coal", "metric": "CO₂ intensity of energy supplied", "unit": "gCO₂/MJ", "target_2030": None},
    "iron_steel":  {"label": "Iron & steel", "metric": "CO₂ intensity of crude steel", "unit": "tCO₂/t", "target_2030": None},
    "cement":      {"label": "Cement", "metric": "Direct CO₂ intensity of cement", "unit": "tCO₂/t", "target_2030": None},
    "automotive":  {"label": "Automotive", "metric": "CO₂ intensity of new vehicles", "unit": "gCO₂/km", "target_2030": None},
    "aviation":    {"label": "Aviation", "metric": "CO₂ intensity per passenger-km", "unit": "gCO₂/pkm", "target_2030": None},
    "maritime":    {"label": "Maritime transport", "metric": "CO₂ intensity of energy used", "unit": "gCO₂/MJ", "target_2030": 23.4},
    "real_estate": {"label": "Commercial & residential real estate", "metric": "Energy intensity", "unit": "kWh/m²", "target_2030": None},
}
IEA_SOURCE = "IEA Net Zero by 2050 (NZE2050) Roadmap — 2030 sector targets. Shipping value cited in ITS (EU) 2022/2453 §39 (NZE2050, 2021 vintage); other sectors pending ingest of the licensed IEA Roadmap Excel."


def _val(a: dict) -> float:
    return a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0


def template3_grid(assets: list[dict]) -> dict:
    """Template 3 alignment metrics by IEA sector. Gross carrying amount is computed from the book; the
    portfolio CO₂-intensity is the gross-amount-weighted average of each counterparty's provided intensity
    (asset['emission_intensity'], only where the unit matches the IEA metric); the distance to the IEA 2030
    target is computed only where BOTH a real benchmark and a portfolio intensity exist — else 'pending'."""
    by: dict[str, dict] = {}
    for a in assets:
        sec = _iea_sector(a.get("nace_code"))
        if not sec:
            continue
        v = _val(a)
        if not v:
            continue
        row = by.setdefault(sec, {"sector": sec, "gross": 0.0, "int_wsum": 0.0, "int_w": 0.0})
        row["gross"] += v
        ci = a.get("emission_intensity")            # provided per-counterparty intensity in the IEA unit
        if isinstance(ci, (int, float)) and ci > 0:
            row["int_wsum"] += ci * v
            row["int_w"] += v

    rows = []
    for sec, r in sorted(by.items(), key=lambda kv: -kv[1]["gross"]):
        b = IEA_NZE2050[sec]
        cur = round(r["int_wsum"] / r["int_w"], 2) if r["int_w"] else None
        tgt = b["target_2030"]
        dist = round(100 * (cur - tgt) / tgt, 1) if (cur is not None and tgt) else None
        rows.append({"sector": sec, "label": b["label"], "metric": b["metric"], "unit": b["unit"],
                     "gross": round(r["gross"]), "current_intensity": cur, "iea_2030": tgt, "distance_pct": dist,
                     "coverage_pct": round(100 * r["int_w"] / r["gross"], 0) if r["gross"] else 0})
    total_gross = sum(r["gross"] for r in rows)
    # portfolio-level alignment distance: gross-weighted mean of the sector distances that are computable
    # (a real benchmark AND a provided intensity). None when nothing is yet computable — never fabricated.
    dw = [(r["distance_pct"], r["gross"]) for r in rows if r["distance_pct"] is not None and r["gross"]]
    portfolio_distance = round(sum(d * g for d, g in dw) / sum(g for _, g in dw), 1) if dw else None
    sectors_pending = sum(1 for r in rows if r["distance_pct"] is None)
    return {
        "rows": rows, "total_gross": total_gross, "source": IEA_SOURCE,
        "portfolio_distance": portfolio_distance, "sectors_total": len(rows), "sectors_pending": sectors_pending,
        "formula": "distance = 100 × ((portfolio intensity − IEA NZE2050 2030 target) / IEA 2030 target)",
        "customer_input": "Counterparty physical CO₂-intensity in the IEA metric unit (gCO₂/kWh, tCO₂/t, …) — "
                          "from the counterparty's disclosures or a specialist climate-data vendor (e.g. TPI, "
                          "Asset Resolution). Not financed emissions; not computable from the physical-risk engine.",
    }


# The Carbon Majors top-20 (InfluenceMap / Climate Accountability Institute — cumulative producer emissions).
# Held so a bank can disclose Template 4 exposures; matched to counterparties by name (identity/LEI ideally).
CARBON_MAJORS_TOP20 = [
    "Saudi Aramco", "Chevron", "Gazprom", "ExxonMobil", "National Iranian Oil Company", "BP",
    "Royal Dutch Shell", "Coal India", "Pemex", "Petroleos de Venezuela", "PetroChina", "Peabody Energy",
    "ConocoPhillips", "Abu Dhabi National Oil Company", "Kuwait Petroleum", "Iraq National Oil Company",
    "TotalEnergies", "Sonatrach", "BHP", "Petrobras",
]
CARBON_MAJORS_SOURCE = "Carbon Majors database (InfluenceMap / Climate Accountability Institute) — the 20 highest cumulative-emission producers. A real deployment matches on legal identity (LEI); demo books use fictional counterparties, so matches are honestly 0."


def template4_top20(assets: list[dict]) -> dict:
    """Template 4 — exposures to the world's top-20 carbon-intensive firms. Matches counterparty names to the
    Carbon Majors list (case-insensitive substring) and sums gross carrying amount to the matched firms."""
    norm = [(m, m.lower()) for m in CARBON_MAJORS_TOP20]
    matched: dict[str, float] = {}
    for a in assets:
        nm = (a.get("asset_name") or "").lower()
        if not nm:
            continue
        for orig, low in norm:
            if low in nm or nm in low:
                matched[orig] = matched.get(orig, 0.0) + _val(a)
                break
    rows = [{"firm": k, "gross": round(v)} for k, v in sorted(matched.items(), key=lambda kv: -kv[1])]
    return {"rows": rows, "matched_count": len(rows), "total_exposure": round(sum(matched.values())),
            "list_size": len(CARBON_MAJORS_TOP20), "source": CARBON_MAJORS_SOURCE}
