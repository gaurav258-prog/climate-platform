"""EBA Pillar 3 ESG — banking-book TRANSITION-risk templates 3 & 4 (ITS (EU) 2022/2453, Annex XXXIX/XL),
built to the ACTUAL regulatory methodology, not a proprietary risk score.

Naming note (added 2026-09-22): the EBA's Final Report on the amended ESG disclosure ITS (EBA/ITS/2026/02,
22 June 2026) renames Template 3 to "EU CRFR4" and DELETES Template 4 entirely (see docs/
GO_LIVE_EXTERNAL_DEPENDENCIES.md #10). That amended ITS is not yet adopted/published in the Official
Journal, so ITS (EU) 2022/2453's Template 3/4 remain the CURRENT, IN-FORCE regulation this module targets —
per the standing rule of always running the currently-adopted version and only cutting over once the new
one is officially published, not on a "Final Report" draft. References below carry both names so this
module doesn't need re-reading from scratch once the cutover happens.

Template 3 / EU CRFR4 (pending adoption) — ALIGNMENT METRICS (Annex XL, §38–41). For each sector for which the IEA defines an alignment
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
counterparties by name/identity; gross carrying amount comes from the book. Per the same EBA/ITS/2026/02
Final Report: Template 4 is not renamed but DELETED outright from the amended ITS (limited prudential
relevance, methodological divergence, overlap with EU CRFR1 per the EBA's own stated reasoning) — kept here
under its current, in-force name until the amended ITS is adopted and Template 4 formally drops.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from services.governance.pillar3_templates import NACE_SECTIONS, _section  # noqa: F401

# Reference data (data/reference/pillar3/, each cited): the Annex XL NACE → IEA sector crosswalk, the IEA NZE2050
# benchmarks and the Carbon Majors top 20. Read here; nothing typed in this module.
_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "pillar3"
_XWALK = json.loads((_REF / "nace_iea_crosswalk.json").read_text())
_ANNEX_XL_NACE_CROSSWALK: tuple[tuple[str, str], ...] = tuple((r["nace"], r["sector"]) for r in _XWALK["crosswalk"])
_CHEMICALS_FALLBACK = _XWALK["chemicals_fallback_division"]


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
    if digits[:2] == _CHEMICALS_FALLBACK:     # chemicals: no published code list — declared fallback (reference file)
        return "chemicals"
    return None


_IEA = json.loads((_REF / "iea_nze2050_benchmarks.json").read_text())
IEA_NZE2050: dict[str, dict] = _IEA["sectors"]
IEA_SOURCE = _IEA["source"]


def _val(a: dict) -> float:
    return a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0


def template3_grid(assets: list[dict]) -> dict:
    """Template 3 / EU CRFR4 (pending adoption) alignment metrics by IEA sector. Gross carrying amount is computed from the book; the
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


_MAJORS = json.loads((_REF / "carbon_majors_top20.json").read_text())
CARBON_MAJORS_TOP20: list[str] = _MAJORS["firms"]
CARBON_MAJORS_SOURCE = _MAJORS["source"]


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
    matched_assets: list[dict] = []
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
                matched_assets.append(a)
                break
    rows = [{"firm": k, "gross": round(v)} for k, v in sorted(matched.items(), key=lambda kv: -kv[1])]
    return {"rows": rows, "matched_count": len(rows), "total_exposure": round(sum(matched.values())), "assets": matched_assets,
            "list_size": len(CARBON_MAJORS_TOP20), "source": CARBON_MAJORS_SOURCE}
