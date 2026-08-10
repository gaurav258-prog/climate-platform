"""The canonical datapoint catalog — single source of truth for WHERE every disclosure datapoint comes from
and HOW it enters Tellumen. Everything downstream derives from this: the filing-coverage map, the Data
Dictionary's source/lane taxonomy, ingestion validation, and the customer-facing data-onboarding guide.

Two axes classify each datapoint:

SOURCE CATEGORY — where the data originates
  tellumen  — our engine + authoritative feeds produce it (the moat: physical & nature risk)
  egov      — a free government/agency dataset we self-integrate as a feed (WDPA, EPC registers, factors)
  evendor   — a commercial 3rd-party dataset the customer licenses (ESG/emissions, carbon tool, controversy)
  customer  — customer-proprietary (their systems, their judgement, their narrative)
  none      — not produced by this platform (a genuine gap / out-of-scope)

INGESTION LANE — how the value reaches a filing
  compute   — Tellumen computes it from its own feeds/engine (no customer step)
  granular  — customer uploads raw records; Tellumen's engine processes them into the value
  provided  — a PRE-CALCULATED value from customer/vendor; Tellumen reconciles it (bring-your-own-number)
  report    — a value/statement needed only on the filing; captured at the form (narrative, flag, final figure)
  none      — n/a (out-of-scope)

The coverage view the customer sees is DERIVED from the lane (see `coverage_source`), so the catalog is the
one place to change when a datapoint's sourcing changes (e.g. a free-gov feed flips an item from
evendor/provided to egov/compute).
"""
from __future__ import annotations


def _dp(key, label, source, lane, provider=None, note=None, recon_tol=None, reconcilable=False):
    # `reconcilable` = though Tellumen computes/estimates this, the customer may PROVIDE their own figure
    # (e.g. an audited number) to reconcile/override it via Lane 2 — a bring-your-own-number cross-check.
    return {"key": key, "label": label, "source_category": source, "lane": lane,
            "provider": provider, "note": note, "recon_tol": recon_tol, "reconcilable": reconcilable}


# lane → the coverage bucket the customer sees on the filing-coverage panel
def coverage_source(lane: str) -> str:
    return {"compute": "computed", "granular": "computed",
            "provided": "integrated", "report": "client"}.get(lane, "out_of_scope")


CATALOG: dict[str, list[dict]] = {
    "bank_tcfd": [
        _dp("phys_risk", "Physical climate-risk exposure — value at risk by hazard, scenario × horizon",
            "tellumen", "compute", provider="Tellumen hazard engine (Copernicus/ECMWF · NASA · USGS feeds)",
            note="You supply the loan book (per-exposure geolocation + value); Tellumen scores every hazard across "
                 "scenarios × horizons and computes value-at-risk — no extra input."),
        _dp("financed_emissions", "Financed emissions — PCAF Scope 1–3",
            "tellumen", "compute", provider="Tellumen PCAF engine", reconcilable=True,
            note="Computed from counterparty emissions; needs an issuer-emissions feed (ESG vendor) or falls back to a NACE-intensity estimate. You can provide an audited PCAF figure to reconcile against it."),
        _dp("taxonomy_eligible", "EU Taxonomy Art. 8 — eligibility (GAR numerator)",
            "tellumen", "compute", provider="Tellumen + your loan book",
            note="From the NACE activity on each exposure; Tellumen classifies which are Taxonomy-eligible."),
        _dp("taxonomy_aligned", "EU Taxonomy Art. 8 — alignment: DNSH + minimum safeguards (→ Green Asset Ratio)",
            "customer", "provided", provider="Your Taxonomy alignment determination (per-exposure flags)",
            note="Only you can attest alignment: substantial-contribution + DNSH + minimum-safeguards per exposure. The loan template already carries a minimum-safeguards field; full alignment (DNSH) is your assessment."),
        _dp("transition_risk", "Transition risk — carbon-price sensitivity / stranded assets",
            "none", "none",
            note="Not modelled by Tellumen: carbon-price / stranded-asset transition sensitivity is a transition-scenario model outside our physical-risk engine."),
        _dp("tcfd_narrative", "TCFD governance, strategy & transition-plan narrative",
            "customer", "report", provider="You author"),
    ],
    "bank_p3esg": [
        _dp("p3_physical", "Template 5 — banking-book exposures to climate physical risk (by geography & sector)",
            "tellumen", "compute", provider="Tellumen hazard engine (Copernicus/ECMWF · NASA · USGS feeds)",
            note="You supply the loan book (per-exposure geolocation, gross carrying amount, NACE sector); Tellumen "
                 "scores every exposure's physical hazards and builds the NACE × geography grid — no extra input."),
        _dp("p3_gar_eligible", "GAR (Templates 7–8) — Taxonomy-eligible exposures",
            "tellumen", "compute", provider="Tellumen + your loan book",
            note="From the NACE activity on each exposure; Tellumen classifies which are Taxonomy-eligible and computes "
                 "the covered-assets denominator (excludes general governments, Art. 7)."),
        _dp("p3_gar_aligned", "GAR — Taxonomy-aligned share (DNSH + minimum safeguards)",
            "customer", "provided", provider="Your Taxonomy alignment determination (per-exposure flags)",
            note="Only YOU can attest alignment: substantial-contribution + DNSH + minimum-safeguards per exposure. "
                 "The loan template already carries a minimum-safeguards field; add the DNSH/alignment flags and we "
                 "compute the Green Asset Ratio and 4-eyes attest it. Until then the aligned share shows 'pending screening'."),
        _dp("p3_scope3", "Financed emissions (Scope 3) for the transition-risk templates",
            "tellumen", "compute", provider="Tellumen PCAF engine", reconcilable=True,
            note="Tellumen computes PCAF-attributed Scope 1–3 from counterparty emissions; needs an issuer-emissions "
                 "feed (ESG vendor) or falls back to a NACE-intensity estimate. You may provide an audited PCAF figure to reconcile."),
        _dp("p3_transition", "Template 3 — transition-risk alignment metrics (banking book)",
            "customer", "provided",
            note="ITS 2022/2453 prescribes a SPECIFIC metric, not a risk score: per IEA sector, the counterparty "
                 "CO₂-INTENSITY alignment metric (e.g. gCO₂/kWh power, gCO₂/MJ shipping, tCO₂/t cement) and its "
                 "DISTANCE to the IEA Net-Zero-by-2050 (NZE2050) 2030 sector target — distance = 100×((current−IEA2030)"
                 "/IEA2030) in %. The binding input is counterparty physical production-intensity data (asset-level / "
                 "counterparty-disclosed / specialist vendor e.g. TPI, Asset Resolution) — NOT computable from our "
                 "physical-risk engine, and distinct from the carbon-PRICE transition score already in the repo (which "
                 "does not satisfy this template). Tellumen supplies the IEA NZE2050 benchmark table + the distance "
                 "calculation + portfolio aggregation; you provide (or we source via vendor) the counterparty intensities."),
        _dp("p3_qualitative", "Templates 1–3 — qualitative ESG risk narrative (governance, strategy, risk mgmt)",
            "customer", "report", provider="You author",
            note="These are the regulator's QUALITATIVE tables — prose describing your governance of ESG risk, business "
                 "strategy and risk-management processes. There is no figure to compute; you write the narrative directly "
                 "on the filing form (we version + attest it with the rest of the filing)."),
    ],
    "reit_tcfd": [
        _dp("phys_risk", "Physical climate-risk to property value + net-operating-income impact",
            "tellumen", "compute", provider="Tellumen hazard engine"),
        _dp("taxonomy_eligible", "EU Taxonomy Art. 8 — eligibility", "tellumen", "compute", provider="Tellumen + your property book"),
        _dp("taxonomy_aligned", "EU Taxonomy Art. 8 — alignment", "customer", "provided", provider="Your Taxonomy alignment determination"),
        _dp("epc", "Energy performance (EPC ratings)", "egov", "provided",
            provider="National EPC registers (UK/IE public) or a property-data vendor",
            note="Free-gov where a public register exists; otherwise a commercial feed. Attached per property."),
        _dp("tcfd_narrative", "TCFD governance & strategy narrative", "customer", "report", provider="You author"),
    ],
    "sfdr_pai": [
        _dp("pai_climate", "PAI 1–6 climate indicators — emissions, carbon footprint, WACI, fossil-fuel, energy",
            "tellumen", "compute", provider="Tellumen PAI engine (from your issuer-data feed)",
            note="Values computed by Tellumen; depend on an issuer ESG/emissions feed (ESG vendor) with a NACE-intensity fallback."),
        _dp("pai_nature", "PAI 7–9 nature indicators — biodiversity, emissions to water, hazardous waste",
            "tellumen", "compute", provider="Tellumen PAI engine (from your issuer-data feed)",
            note="PAI 7 (biodiversity areas) could move to Tellumen-computed via the free WDPA/Natura 2000 feed (roadmap)."),
        _dp("pai_social", "PAI 10–14 social & governance indicators — UNGC/OECD, gender pay, board, weapons",
            "tellumen", "compute", provider="Tellumen PAI engine (from your issuer-data feed)",
            note="UNGC signatory status is free-gov; violation/weapons screening is a vendor feed; UK gender-pay-gap is free-gov."),
        _dp("pai_additional", "Additional / opt-in PAI indicators (Tables 2–3)",
            "evendor", "provided", provider="Issuer ESG data feed (ESG vendor)"),
        _dp("sfdr_narrative", "Narratives — policies, actions, engagement, reference standards",
            "customer", "report", provider="You author (in-product narratives editor)"),
    ],
    "csrd_e1": [
        _dp("e1_financial_effects", "ESRS E1-9 — physical-risk anticipated financial effects (own ops + upstream)",
            "tellumen", "compute", provider="Tellumen E1 engine"),
        _dp("e1_ghg", "ESRS E1-6 — GHG emissions (Scope 1–3) & energy",
            "evendor", "provided", provider="Your carbon-accounting tool (Watershed/Persefoni/…)",
            note="We ingest + reconcile the inventory; activity data is yours, emission factors are free-gov."),
        _dp("e1_transition", "ESRS E1-1/4 — transition plan, targets, carbon price", "none", "none"),
        _dp("e1_narrative", "ESRS E1 — governance & impact/risk/opportunity narrative", "customer", "report", provider="You author"),
    ],
    "esrs_pack": [
        _dp("e1_financial_effects", "ESRS E1-9 — physical-risk anticipated financial effects",
            "tellumen", "compute", provider="Tellumen E1 engine"),
        _dp("e3_water", "ESRS E3-4 — water-stress exposure (own ops + upstream) · PROXY",
            "tellumen", "compute", provider="Tellumen hazard engine (water-stress / soil-water)",
            note="ESRS E3-4 mandates METERED water consumption (m³) and intensity (m³ per €m net revenue). This "
                 "is a water-STRESS exposure indicator (hazard-based), a proxy for E3-4 site risk — it is NOT the "
                 "metered consumption figure. Report the metered m³ via 'e3_measured_water'; use this to prioritise "
                 "which sites/plots to meter and to disclose the water-risk context E3-4 also asks for."),
        _dp("e4_deforestation", "ESRS E4 — deforestation determination (EUDR, satellite)",
            "tellumen", "compute", provider="Tellumen deforestation engine (Hansen Global Forest Change)"),
        _dp("e4_protected_area", "ESRS E4 — own sites / sourcing plots in or near a protected area",
            "egov", "compute", provider="EEA Natura 2000 + OpenStreetMap (free-gov feeds, H3 overlap)", reconcilable=True,
            note="Computed from free EU (Natura 2000) + global (OSM) feeds. A customer holding the authoritative "
                 "WDPA (via IBAT) can PROVIDE their count to reconcile/override ours — zero data cost to us."),
        _dp("e1_ghg", "ESRS E1-6 — GHG emissions (Scope 1–3) & energy",
            "evendor", "provided", provider="Your carbon-accounting tool"),
        _dp("e3_measured_water", "ESRS E3-4 — metered water consumption (m³) + intensity (m³/€m revenue)",
            "customer", "provided", provider="Your site water meters",
            note="The mandated E3-4 metric: total water consumption in m³ and consumption intensity per €m net "
                 "revenue. Metered operational data — provide it here; our water-stress indicator (e3_water) is the "
                 "risk-context proxy, not a substitute for the meter reading."),
        _dp("esrs_narrative", "ESRS — transition plan & narrative", "customer", "report", provider="You author"),
    ],
    "insurer_climate": [
        _dp("natcat_eal", "NatCat expected annual loss + loss ratio by peril",
            "tellumen", "compute", provider="Tellumen NatCat engine"),
        _dp("sum_insured_at_risk", "Sum insured at risk (High+) by peril & geography",
            "tellumen", "compute", provider="Tellumen hazard engine + your SoV"),
        _dp("uw_narrative", "Underwriting strategy & climate narrative", "customer", "report", provider="You author"),
    ],
    "eudr_dds": [
        _dp("eudr_determination", "Per-plot geolocation + deforestation-free determination (satellite vs 2020 cutoff)",
            "tellumen", "compute", provider="Tellumen (your plot polygons + Hansen Global Forest Change)"),
        _dp("eudr_legality", "Legality evidence + supplier declarations",
            "customer", "provided", provider="Your supplier legality documentation"),
    ],
}


def catalog(framework: str) -> list[dict] | None:
    """The datapoints for a framework, each with source-category + ingestion lane + provider."""
    return CATALOG.get(framework)


def coverage(framework: str) -> dict | None:
    """Filing coverage DERIVED from the catalog: each datapoint's lane → a coverage bucket, plus a summary
    (how much of this filing we produce from your data). Same shape the coverage panel already consumes."""
    dps = CATALOG.get(framework)
    if not dps:
        return None
    sections = [{"section": d["label"], "source": coverage_source(d["lane"]),
                 "source_category": d["source_category"], "lane": d["lane"], "provider": d["provider"],
                 "note": d.get("note"), "reconcilable": d.get("reconcilable", False)} for d in dps]
    srcs = ("computed", "integrated", "client", "out_of_scope")
    counts = {k: sum(1 for s in sections if s["source"] == k) for k in srcs}
    total = len(sections)
    return {"sections": sections, "counts": counts, "total": total,
            "pct_computed": round(100 * counts["computed"] / total) if total else 0}
