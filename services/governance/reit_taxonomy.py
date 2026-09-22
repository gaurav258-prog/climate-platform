"""EU Taxonomy Article 8 KPIs for a real-estate undertaking (REIT) — the disclosure the generic located-book
form was missing.

Regulation: Commission Delegated Regulation (EU) 2021/2178 (Article 8 disclosures), read with the Climate
Delegated Act (EU) 2021/2139 Annex I §7.7 "Acquisition and ownership of buildings". A non-financial
undertaking discloses THREE KPIs — the proportion of Turnover, CapEx and OpEx that is Taxonomy-eligible and,
of that, Taxonomy-aligned.

What we compute vs declare — same honesty discipline as the banking Pillar 3 build (compute what the golden
source genuinely supports; declare the rest; never fabricate):
  • TURNOVER KPI — computed. Del. Reg. (EU) 2021/2178 Annex I §1.1.1: the denominator is net turnover per
    Article 2(5) of Directive 2013/34/EU / IAS 1 para 82(a) -- GROSS revenue before operating expenses. Per-
    property annual_gross_rental_revenue_eur is the turnover weight when supplied; a building owned/let is the
    eligible activity §7.7. Where a property has no gross-revenue figure on file, annual_noi_eur (revenue MINUS
    opex) is used as a disclosed fallback proxy -- this UNDERSTATES true turnover, and is flagged per-property
    and in aggregate so it's never silently mistaken for the real denominator.
  • ALIGNMENT — NOT asserted (held at 0, disclosed). Per ml/regulatory/eu_taxonomy_classifier, "aligned" needs
    substantial contribution + DNSH across all objectives + minimum safeguards, which cannot be fully verified
    from collected data. We surface the VERIFIABLE sub-signals instead of a fabricated aligned figure:
    EPC-based substantial contribution (Annex I §7.7 point 1: EPC class A only), the platform's physical-risk
    assessment as the climate-change-ADAPTATION DNSH evidence (Article 17), and the minimum-safeguards flag.
  • CAPEX / OPEX KPIs — declared, not computed: they need the undertaking's capex/opex ledger, which is not
    derivable from asset location. Shown in the same eligible/aligned/non-eligible row shape as the turnover
    KPI (Del. Reg. 2021/2178 Annex II), with every figure "—" (declared) rather than fabricated, so a renderer
    can lay out the full three-KPI Annex II grid from this one structure.
"""
from __future__ import annotations

_ELIGIBLE = "eligible"
_SC_EPC = frozenset({"A"})               # Annex I §7.7 point 1: EPC class A is the substantial-contribution bar
                                          # (B does NOT qualify; the top-15%-of-stock alternative is unevaluated)
_HIGH = frozenset({"H", "VH"})           # physical-risk bands that WEAKEN the climate-adaptation DNSH case

_KPI_ROW_LABELS = ["Taxonomy-eligible turnover", "of which Taxonomy-aligned",
                   "Taxonomy-eligible but not verified aligned", "Taxonomy-non-eligible turnover"]


def _pct(n: float, d: float) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def _turnover_base(p: dict) -> tuple[float, bool]:
    """(value, is_noi_proxy). Real gross rental revenue when supplied (the correct Annex I §1.1.1 basis);
    else annual_noi_eur as a disclosed, understating fallback."""
    gross = p.get("annual_gross_rental_revenue_eur")
    if gross is not None:
        return float(gross), False
    return float(p.get("annual_noi_eur") or 0), True


def art8_kpis(properties: list[dict]) -> dict:
    """Article 8 KPI block for the REIT property book. `properties` = the realestate disclosure snapshot rows."""
    bases = [_turnover_base(p) for p in properties]
    total_to = sum(v for v, _ in bases)
    n_proxy = sum(1 for _, is_proxy in bases if is_proxy)
    proxy_to = sum(v for v, is_proxy in bases if is_proxy)

    elig_idx = [i for i, p in enumerate(properties) if p.get("taxonomy_status") == _ELIGIBLE]
    elig = [properties[i] for i in elig_idx]
    elig_to = sum(bases[i][0] for i in elig_idx)

    # verifiable sub-signals over the ELIGIBLE turnover (evidence toward alignment — never asserted as aligned)
    sc_epc_to = sum(bases[i][0] for i in elig_idx if (properties[i].get("epc_rating") or "").upper() in _SC_EPC)
    dnsh_adapt_to = sum(bases[i][0] for i in elig_idx if properties[i].get("headline_bucket") not in _HIGH)
    safeguards_to = sum(bases[i][0] for i in elig_idx
                        if (properties[i].get("taxonomy_reasoning") or {}).get("minimum_safeguards_verified") is True)

    basis_note = ("Turnover basis: annual_gross_rental_revenue_eur (Del. Reg. (EU) 2021/2178 Annex I §1.1.1 — "
                  "gross revenue, IAS 1 para 82(a)) where supplied. Eligible activity: Climate Delegated Act "
                  "(EU) 2021/2139 Annex I §7.7 — Acquisition and ownership of buildings.")
    if n_proxy:
        basis_note += (f" {n_proxy} of {len(properties)} propert{'y' if n_proxy == 1 else 'ies'} "
                       f"(€{round(proxy_to):,} of turnover) had no gross-revenue figure on file and fall back to "
                       f"annual_noi_eur (net operating income) as a proxy — this UNDERSTATES true turnover, since "
                       f"NOI is revenue net of operating expenses, not gross revenue.")

    turnover_kpi = {
        "basis": basis_note,
        "total_eur": round(total_to),
        "noi_proxy_used": n_proxy > 0,
        "n_properties_using_noi_proxy": n_proxy,
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
            "note": "Substantial contribution requires EPC class A (Annex I §7.7 point 1 — B does NOT qualify; "
                    "the top-15%-of-national-stock alternative route is a separate, unevaluated test). "
                    "Climate-adaptation DNSH (Art. 17) uses the platform's own physical-risk assessment: a "
                    "property NOT in the top-two hazard bands has a favourable adaptation case. These are "
                    "evidence toward alignment, not a claim.",
        },
    }

    def _declared_kpi(kpi_name: str, annex_citation: str) -> dict:
        # Same row shape as turnover_kpi (label/eur/pct), so a renderer can build one Annex II grid from all
        # three KPIs — but every figure is None (declared, not computed): a REIT's capex/opex ledger by
        # Taxonomy-eligible activity is not derivable from asset location.
        return {
            "status": "declared_customer_data",
            "basis": f"{kpi_name} KPI requires the undertaking's {kpi_name.lower()} ledger by economic activity "
                     f"(Del. Reg. 2021/2178 Annex I §{annex_citation}) — not derivable from asset location.",
            "total_eur": None,
            "rows": [{"row": label, "eur": None, "pct": None} for label in _KPI_ROW_LABELS],
            "note": "Provide the ledger to populate; the eligible-activity mapping (§7.7) and the alignment "
                    "evidence above then apply per line.",
        }

    return {
        "framework": "reit_taxonomy",
        "regulation": "Commission Delegated Regulation (EU) 2021/2178, Article 8; Climate Delegated Act "
                      "(EU) 2021/2139 Annex I §7.7",
        "n_properties": len(properties),
        "turnover_kpi": turnover_kpi,
        "capex_kpi": _declared_kpi("CapEx", "1.1.2"),
        "opex_kpi": _declared_kpi("OpEx", "1.1.3"),
        "customer_columns": ["CapEx by activity (Annex I §1.1.2)", "OpEx by activity (Annex I §1.1.3)",
                             "minimum-safeguards attestation", "DNSH across the five non-adaptation objectives"],
    }
