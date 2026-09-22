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

import re

from services.governance.pillar3_templates import NACE_SECTIONS, _section  # noqa: F401


# NACE → IEA Template-3 sector — the OFFICIAL crosswalk table, not a division-level heuristic. Annex XL of
# the adopted ITS embeds "List of NACE sectors to be considered" as a table (a scanned image inside the
# Official Journal document itself, extracted and read directly: scripts/fetch_eu_regulation.sh 32022R2453,
# then OCR'd the embedded JPEG at the "Template 3: Banking book" caption). It lists 8 mandatory Template-3
# sectors — power, fossil fuel combustion, cement, iron & steel, chemicals, automotive, aviation, maritime
# transport (no "aluminium," no "real estate" — those were an earlier version's invented entries, corrected)
# — each with its OWN explicit NACE code list, not a clean division-level split. Three real findings from
# reading the actual table, none obvious from the division numbers alone:
#   • NACE division 5 (mining of coal and lignite) is listed under "Iron and steel, coke, and metal ore
#     production," NOT "Fossil fuel combustion" — coking coal feeding steel production is grouped with steel,
#     not with the fossil-fuel-combustion sector's own "coal" sub-list (NACE divisions 8 and 9 only).
#   • The table's own PRINTED codes drop the leading zero that single-digit NACE divisions (5,6,7,8,9)
#     normally carry (e.g. it prints "51" for what real NACE calls "05.1" — verified against the actual NACE
#     Rev. 2 explanatory text, scripts/fetch_eu_regulation.sh 32006R1893: 05.1/05.10 = coal mining, 06.1/06.10
#     = crude-oil extraction, 07.2/07.29 = non-ferrous metal ore mining, 08.9 = other mining/quarrying n.e.c.,
#     09.1/09.10 = petroleum/gas support activities). Read literally, "51"/"61"/"72"/"89"/"91" would collide
#     with the REAL, unrelated 2-digit divisions 51 (air transport), 61 (telecoms), 72 (scientific R&D), 91
#     (libraries/museums) — so every such entry below is stored WITH the leading zero restored (e.g. "051",
#     not "51"), which also naturally disambiguates it from those real divisions via prefix length.
#   • The table's codes otherwise mix NACE divisions (2-digit), groups (3-digit) and classes (4-digit) with
#     one deliberate override (NACE class 20.14, oil-derived organic chemicals, is carved out to oil_gas
#     specifically, not the chemicals fallback below) — matching is by longest-listed-prefix throughout.
# "Chemicals" (sector 8 in the summary list) has NO published NACE code list in this table at all — every
# other sector's codes are given, chemicals' column is simply blank in the source. NACE division 20
# ("manufacture of chemicals and chemical products") is used as a reasonable, disclosed fallback — this is
# the one sector in this crosswalk NOT sourced from the official table itself, because the table doesn't
# provide one.
_ANNEX_XL_NACE_CROSSWALK: tuple[tuple[str, str], ...] = (
    # Maritime transport (shipping) — division 50 (real, ≥10, no leading-zero issue)
    ("301", "maritime"), ("3011", "maritime"), ("3012", "maritime"), ("3315", "maritime"),
    ("50", "maritime"), ("501", "maritime"), ("5010", "maritime"), ("502", "maritime"), ("5020", "maritime"),
    ("5222", "maritime"), ("5224", "maritime"), ("5229", "maritime"),
    # Power — divisions 27/33/35/43 (all real, ≥10)
    ("27", "power"), ("2712", "power"), ("3314", "power"), ("35", "power"), ("351", "power"),
    ("3511", "power"), ("3512", "power"), ("3513", "power"), ("3514", "power"), ("4321", "power"),
    # Fossil fuel combustion — oil and gas. "091"/"0910" = group/class 09.1 (support activities for petroleum
    # & gas extraction — real NACE division 9, NOT division 91). "06"/"061"/"0610"/"062"/"0620" = division 6
    # (extraction of crude petroleum & natural gas) and its groups/classes — NOT division 61 (telecoms).
    ("091", "oil_gas"), ("0910", "oil_gas"), ("192", "oil_gas"), ("1920", "oil_gas"), ("2014", "oil_gas"),
    ("352", "oil_gas"), ("3521", "oil_gas"), ("3522", "oil_gas"), ("3523", "oil_gas"),
    ("4612", "oil_gas"), ("4671", "oil_gas"), ("06", "oil_gas"), ("061", "oil_gas"), ("0610", "oil_gas"),
    ("062", "oil_gas"), ("0620", "oil_gas"),
    # Fossil fuel combustion — coal. Bare divisions 8 ("other mining and quarrying") and 9 ("mining support
    # service activities") themselves — real NACE, leading zero restored ("08"/"09", not "8"/"9").
    ("08", "coal"), ("09", "coal"),
    # Iron and steel, coke, and metal ore production — "steel" sub-list (divisions 24/25/46, all real, ≥10;
    # "072"/"0729" = group/class 07.2 non-ferrous metal ore mining — real NACE division 7, NOT division 72)
    ("24", "iron_steel"), ("241", "iron_steel"), ("2410", "iron_steel"), ("242", "iron_steel"),
    ("2420", "iron_steel"), ("2434", "iron_steel"), ("244", "iron_steel"), ("2442", "iron_steel"),
    ("2444", "iron_steel"), ("2445", "iron_steel"), ("245", "iron_steel"), ("2451", "iron_steel"),
    ("2452", "iron_steel"), ("25", "iron_steel"), ("251", "iron_steel"), ("2511", "iron_steel"),
    ("4672", "iron_steel"), ("07", "iron_steel"), ("072", "iron_steel"), ("0729", "iron_steel"),
    # Iron and steel, coke, and metal ore production — "coal" sub-list. Division 5 (mining of coal/lignite)
    # and its groups/classes — real NACE division 5, NOT the unrelated division 51 (air transport) or 52
    # (warehousing). This is the real, previously-miscoded discrepancy the primary table caught: coking coal
    # is grouped with steel production here, NOT with "Fossil fuel combustion" above.
    ("05", "iron_steel"), ("051", "iron_steel"), ("0510", "iron_steel"), ("052", "iron_steel"), ("0520", "iron_steel"),
    # Cement, clinker and lime production. "089" = group/class 08.9 (mining/quarrying n.e.c. — stone, sand,
    # clay for cement raw materials — real NACE division 8, overriding the bare "08"→coal default above via
    # longest-prefix-wins). "811" is division 81 (real, ≥10), unrelated to the leading-zero issue.
    ("235", "cement"), ("2351", "cement"), ("2352", "cement"), ("236", "cement"), ("2361", "cement"),
    ("2363", "cement"), ("2364", "cement"), ("811", "cement"), ("089", "cement"),
    # Aviation — division 51/52 (real, ≥10 — genuinely "Air transport" / "Warehousing and support activities
    # for transportation," no leading-zero ambiguity here since these ARE the real 2-digit divisions)
    ("3030", "aviation"), ("3316", "aviation"), ("511", "aviation"), ("5110", "aviation"),
    ("512", "aviation"), ("5121", "aviation"), ("5223", "aviation"),
    # Automotive — division 28/29 (real, ≥10). NACE 30 "other transport equipment" is absent from
    # AUTOMOTIVE's own list specifically — but the table folds two of its classes in elsewhere: 30.11/30.12
    # (shipbuilding) under maritime and 30.30 (aircraft manufacture) under aviation, above. Only the
    # remaining NACE 30 classes (30.20 railway, 30.91/30.92 motorcycles/bicycles, etc.) stay unmapped.
    ("2815", "automotive"), ("29", "automotive"), ("291", "automotive"), ("2910", "automotive"),
    ("292", "automotive"), ("2920", "automotive"), ("293", "automotive"), ("2932", "automotive"),
)


def _iea_sector(nace_code) -> str | None:
    if not nace_code:
        return None
    digits = "".join(ch for ch in str(nace_code) if ch.isdigit())
    if not digits:
        return None
    # longest-listed-code-first: a class-level entry (e.g. "2451") should win over a broader division-level
    # entry for the same sector (e.g. "24") when both match, and — critically for the leading-zero-restored
    # entries above — a real 2-digit division (e.g. "51" air transport) never gets shadowed by a same-digit
    # single-digit-division sub-code, because the sub-code is stored WITH its leading zero ("051") and so
    # can never be a prefix-match for an input that doesn't itself start with "0".
    best: tuple[str, str] | None = None
    for code, sector in _ANNEX_XL_NACE_CROSSWALK:
        if digits.startswith(code) and (best is None or len(code) > len(best[0])):
            best = (code, sector)
    if best:
        return best[1]
    if digits[:2] == "20":             # chemicals — see module-level note: not in the official table itself
        return "chemicals"
    return None


# IEA NZE2050 alignment metric + 2030 target per sector. `target_2030` is only populated where a citable
# value exists (shipping, from ITS 2022/2453 §39 worked example); the rest are None='pending IEA ingest'
# so a distance is only ever shown against a REAL benchmark — never a guessed one.
IEA_NZE2050: dict[str, dict] = {
    "power":       {"label": "Power generation", "metric": "CO₂ intensity of generation", "unit": "gCO₂/kWh", "target_2030": None},
    "oil_gas":     {"label": "Oil & gas", "metric": "CO₂ intensity of energy supplied", "unit": "gCO₂/MJ", "target_2030": None},
    "coal":        {"label": "Coal", "metric": "CO₂ intensity of energy supplied", "unit": "gCO₂/MJ", "target_2030": None},
    "iron_steel":  {"label": "Iron & steel", "metric": "CO₂ intensity of crude steel", "unit": "tCO₂/t", "target_2030": None},
    "chemicals":   {"label": "Chemicals", "metric": "CO₂ intensity of chemical production", "unit": "tCO₂/t", "target_2030": None},
    "cement":      {"label": "Cement", "metric": "Direct CO₂ intensity of cement", "unit": "tCO₂/t", "target_2030": None},
    "automotive":  {"label": "Automotive", "metric": "CO₂ intensity of new vehicles", "unit": "gCO₂/km", "target_2030": None},
    "aviation":    {"label": "Aviation", "metric": "CO₂ intensity per passenger-km", "unit": "gCO₂/pkm", "target_2030": None},
    "maritime":    {"label": "Maritime transport", "metric": "CO₂ intensity of energy used", "unit": "gCO₂/MJ", "target_2030": 23.4},
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


def _normalize_name(name: str) -> str:
    """Hyphens and slashes count as \\W (word-boundary) characters, so a raw word-boundary match on a
    hyphenated legal-name rendering (e.g. "Royal-Dutch-Shell", a real-world loan-tape normalization pattern)
    would otherwise never match the space-separated "royal dutch shell" list entry — treat them as spaces."""
    return re.sub(r"[-/]", " ", name)


def template4_top20(assets: list[dict]) -> dict:
    """Template 4 — exposures to the world's top-20 carbon-intensive firms. Matches counterparty names to the
    Carbon Majors list (case-insensitive, WORD-boundary matching — not a raw substring test) and sums gross
    carrying amount to the matched firms. Word-boundary matters here specifically because several Carbon
    Majors names are short (BP, BHP): a raw substring test would false-positive on any unrelated counterparty
    whose name happens to contain "bp" mid-word (e.g. a fictional "Kabpur Textiles"); requiring the match sit
    between non-word characters (or string start/end) rules that out while still matching "BP plc", "BP
    Global Trading", etc. The reverse direction (the counterparty's OWN name is a fragment of a major's full
    name — e.g. "Shell" matching "Royal Dutch Shell") is gated to counterparty names of 4+ characters to rule
    out the shortest fragments; it does NOT fully close the risk of a short generic/country word (e.g. a
    fictional counterparty literally named "Kuwait") false-positive-matching "Kuwait Petroleum" — length alone
    can't distinguish a legitimate short brand form ("Shell") from a coincidental generic word, and this is a
    disclosed, accepted residual limitation of name-matching (not real LEI/legal-identity matching — see
    CARBON_MAJORS_SOURCE)."""
    norm = [(m, re.escape(_normalize_name(m).lower())) for m in CARBON_MAJORS_TOP20]
    matched: dict[str, float] = {}
    for a in assets:
        raw_nm = a.get("asset_name") or ""
        nm = _normalize_name(raw_nm).lower()
        if not nm:
            continue
        for orig, low_pat in norm:
            forward = re.search(rf"(?:^|\W){low_pat}(?:$|\W)", nm)
            reverse = len(nm) >= 4 and re.search(rf"(?:^|\W){re.escape(nm)}(?:$|\W)", _normalize_name(orig).lower())
            if forward or reverse:
                matched[orig] = matched.get(orig, 0.0) + _val(a)
                break
    rows = [{"firm": k, "gross": round(v)} for k, v in sorted(matched.items(), key=lambda kv: -kv[1])]
    return {"rows": rows, "matched_count": len(rows), "total_exposure": round(sum(matched.values())),
            "list_size": len(CARBON_MAJORS_TOP20), "source": CARBON_MAJORS_SOURCE}
