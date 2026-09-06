"""EU Taxonomy Article 8 KPIs for a real-estate undertaking (REIT) — the disclosure the generic located-book
form was missing.

Regulation: Commission Delegated Regulation (EU) 2021/2178 (Article 8 disclosures), read with the Climate
Delegated Act (EU) 2021/2139 Annex I §7.7 "Acquisition and ownership of buildings". A non-financial
undertaking discloses THREE KPIs — the proportion of Turnover, CapEx and OpEx that is Taxonomy-eligible and,
of that, Taxonomy-aligned.

What we compute vs declare — same honesty discipline as the banking Pillar 3 build (compute what the golden
source genuinely supports; declare the rest; never fabricate):
  • TURNOVER KPI — computed. Per-property rental income (annual_noi_eur) is the turnover weight; a building
    owned/let is the eligible activity §7.7. So eligible-turnover % is real.
  • ALIGNMENT — NOT asserted (held at 0, disclosed). Per ml/regulatory/eu_taxonomy_classifier, "aligned" needs
    substantial contribution + DNSH across all objectives + minimum safeguards, which cannot be fully verified
    from collected data. We surface the VERIFIABLE sub-signals instead of a fabricated aligned figure:
    EPC-based substantial contribution (Annex I §7.7 TSC proxy), the platform's physical-risk assessment as the
    climate-change-ADAPTATION DNSH evidence (Article 17), and the minimum-safeguards flag.
  • CAPEX / OPEX KPIs — declared, not computed: they need the undertaking's capex/opex ledger, which is not
    derivable from asset location. Shown as required rows with the datapoint owner named.
"""
from __future__ import annotations

_ELIGIBLE = "eligible"
_SC_EPC = frozenset({"A", "B"})          # EPC A/B — disclosed proxy for §7.7 top-of-market substantial contribution
_HIGH = frozenset({"H", "VH"})           # physical-risk bands that WEAKEN the climate-adaptation DNSH case


def _pct(n: float, d: float) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def art8_kpis(properties: list[dict]) -> dict:
    """Article 8 KPI block for the REIT property book. `properties` = the realestate disclosure snapshot rows."""
    total_to = sum((p.get("annual_noi_eur") or 0) for p in properties)          # turnover proxy = rental income
    elig = [p for p in properties if p.get("taxonomy_status") == _ELIGIBLE]
    elig_to = sum((p.get("annual_noi_eur") or 0) for p in elig)

    # verifiable sub-signals over the ELIGIBLE turnover (evidence toward alignment — never asserted as aligned)
    sc_epc_to = sum((p.get("annual_noi_eur") or 0) for p in elig if (p.get("epc_rating") or "").upper() in _SC_EPC)
    dnsh_adapt_to = sum((p.get("annual_noi_eur") or 0) for p in elig if p.get("headline_bucket") not in _HIGH)
    safeguards_to = sum((p.get("annual_noi_eur") or 0) for p in elig
                        if (p.get("taxonomy_reasoning") or {}).get("minimum_safeguards_verified") is True)

    turnover_kpi = {
        "basis": "Turnover proxied by annual rental income (annual_noi_eur). Eligible activity: Climate "
                 "Delegated Act (EU) 2021/2139 Annex I §7.7 — Acquisition and ownership of buildings.",
        "total_eur": round(total_to),
        "rows": [
            {"row": "Taxonomy-eligible turnover", "eur": round(elig_to), "pct": _pct(elig_to, total_to)},
            {"row": "of which Taxonomy-aligned", "eur": 0, "pct": 0.0,
             "note": "Not asserted — full alignment (substantial contribution + DNSH all objectives + minimum "
                     "safeguards) is not verifiable from collected data; see the sub-signals below. Disclosed, "
                     "never fabricated."},
            {"row": "Taxonomy-eligible but not verified aligned", "eur": round(elig_to), "pct": _pct(elig_to, total_to)},
            {"row": "Taxonomy-non-eligible turnover", "eur": round(total_to - elig_to),
             "pct": _pct(total_to - elig_to, total_to)},
        ],
        # the verifiable evidence a reviewer/supervisor can act on, as % of eligible turnover
        "alignment_evidence": {
            "substantial_contribution_epc_ab_pct": _pct(sc_epc_to, elig_to),
            "climate_adaptation_dnsh_favourable_pct": _pct(dnsh_adapt_to, elig_to),
            "minimum_safeguards_verified_pct": _pct(safeguards_to, elig_to),
            "note": "Substantial contribution proxied by EPC A/B (§7.7 TSC). Climate-adaptation DNSH (Art. 17) "
                    "uses the platform's own physical-risk assessment: a property NOT in the top-two hazard "
                    "bands has a favourable adaptation case. These are evidence toward alignment, not a claim.",
        },
    }

    declared = {
        "status": "declared_customer_data",
        "note": "CapEx/OpEx KPIs require the undertaking's capex/opex ledger (Del. Reg. 2021/2178 Annex I §1.1.2/"
                "1.1.3) — not derivable from asset location. Provide it to populate; the eligible-activity "
                "mapping (§7.7) and the alignment evidence above then apply per line.",
    }

    return {
        "framework": "reit_taxonomy",
        "regulation": "Commission Delegated Regulation (EU) 2021/2178, Article 8; Climate Delegated Act "
                      "(EU) 2021/2139 Annex I §7.7",
        "n_properties": len(properties),
        "turnover_kpi": turnover_kpi,
        "capex_kpi": declared,
        "opex_kpi": declared,
        "customer_columns": ["CapEx by activity (Annex I §1.1.2)", "OpEx by activity (Annex I §1.1.3)",
                             "minimum-safeguards attestation", "DNSH across the five non-adaptation objectives"],
    }
