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


# Report types whose provided values belong to one undertaking: Solvency II states own funds, the SCR, the reinsurance in
# force and the nat-cat premiums per insurance undertaking and, separately, for the group (Directive 2009/138/EC Arts 100,
# 218 ff.) — a solo filing uses its entity's own figures, a group filing the group's; never borrowed across.
PER_ENTITY_REPORTS = frozenset({"insurer_solvency", "insurer_orsa_climate", "insurer_recovery_stress",
                                "esrs"})   # ESRS figures: per undertaking (Art. 19a) or for the group (Art. 29a, its parent)

CATALOG: dict[str, list[dict]] = {
    # the EU Taxonomy Art. 8 report (E95): what the Annex VI templates read — physical risk, financed emissions and
    # transition risk left with the TCFD sections (they are Pillar 3's, or live analytics)
    "bank_tcfd": [
        _dp("taxonomy_eligible", "EU Taxonomy Art. 8 — eligibility of each exposure (Annex VI Templates 1–4)",
            "tellumen", "compute", provider="Tellumen + your loan book",
            note="From the NACE activity, counterparty and instrument on each exposure; the specification of the version "
                 "in force places it in its template row."),
        _dp("taxonomy_aligned", "EU Taxonomy Art. 8 — alignment (→ Green Asset Ratio)",
            "customer", "provided", provider="Your Taxonomy alignment determination; the counterparty's own Taxonomy KPIs",
            note="Specific-purpose lending: the exposure's own aligned status, objective and contribution, which you "
                 "determine. General-purpose lending to an undertaking: the counterparty's own turnover / CapEx KPIs "
                 "(issuer Taxonomy KPIs on file) — never estimated; blank where none is on file."),
        _dp("taxonomy_entered", "Annex VI KPIs the loan tape holds no facts for (off-balance-sheet, fees and commissions, "
                                "trading book)",
            "customer", "report", provider="You enter them on the filing form",
            note="Each cell is entered for the reporting period and attested by a second person; the form gives the "
                 "reason the platform cannot compute it."),
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
            note="Tellumen computes PCAF-attributed Scope 1–3 from counterparty emissions (reported, or a "
                 "NACE-intensity estimate where an issuer-emissions feed is missing), weighted by the PCAF "
                 "attribution factor (outstanding ÷ counterparty EVIC, capped at 100%). Counterparty EVIC is a "
                 "required loan-tape field for new loans; a loan without it is excluded from this figure, "
                 "never counted unweighted. You may provide an audited PCAF figure to reconcile."),
        _dp("p3_transition_align", "Template 3 / EU CRFR4 (pending adoption) — transition-risk alignment metrics (IEA NZE2050 distance)",
            "customer", "provided", provider="Counterparty CO₂-intensity feed (climate-data vendor / counterparty)",
            note="ITS 2022/2453 prescribes a SPECIFIC metric: per IEA sector, the portfolio CO₂-INTENSITY (gCO₂/kWh, "
                 "gCO₂/MJ, tCO₂/t) and its DISTANCE to the IEA NZE2050 2030 target = 100×((current−IEA2030)/IEA2030). "
                 "Tellumen builds the NACE→IEA crosswalk, the benchmark table + the distance/aggregation; the binding "
                 "input — each counterparty's PHYSICAL production-intensity — is not computable from our physical-risk "
                 "engine, so you provide it (vendor feed or counterparty disclosure). Shows 'pending' until fed."),
        _dp("p3_transition_top20", "Template 4 (deleted by the pending EBA/ITS/2026/02 amendment) — exposures to the top-20 carbon-intensive firms",
            "tellumen", "compute", provider="Tellumen (Carbon Majors list) + your loan book",
            note="Tellumen holds the published Carbon Majors top-20 list and matches your counterparties (by legal "
                 "identity/LEI) to it; gross carrying amount comes from your book. No external feed needed."),
        _dp("p3_qualitative", "Tables 1–3 — qualitative ESG risk narrative (governance, strategy, risk mgmt)",
            "customer", "report", provider="You author",
            note="These are the regulator's QUALITATIVE tables — prose describing your governance of ESG risk, business "
                 "strategy and risk-management processes. There is no figure to compute; you write the narrative directly "
                 "on the filing form, for the filing's institution and reference date; the filing freezes it with its "
                 "figures, prints it, and is blocked while a row is unanswered."),
    ],
    # reit_tcfd, insurer_climate: retired (services.governance.filings.FRAMEWORKS) — they take no provided value
    # (provided_data.submit) and no prior-filing upload, so they list no datapoints; csrd_e1 keeps its own for the labels
    # of its confirmed prior filings
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
    # Solvency II: the nat-cat SCR is computed; the undertaking's capital position and the reinsurance programme in force
    # come from its own records (S.23.01 own funds, the SCR / MCR it reports, its treaties) — stated once here, attested
    # under four eyes, and read by every insurer report that needs them (ORSA climate analysis, recovery stress, net losses)
    "insurer_solvency": [
        _dp("natcat_scr", "Nat-cat SCR — standard formula (Del. Reg. 2015/35 Art. 120-125) and the modelled 1-in-200",
            "tellumen", "compute", provider="Tellumen nat-cat engine + your statement of values"),
        {**_dp("eligible_own_funds_scr", "Eligible own funds to meet the SCR", "customer", "provided",
               provider="Your Solvency II own-funds return (S.23.01)",
               note="The total eligible own funds to meet the Solvency Capital Requirement, for the reporting date."), "unit": "EUR"},
        {**_dp("scr_total", "Solvency Capital Requirement (total)", "customer", "provided",
               provider="Your Solvency II SCR calculation (S.25)",
               note="The SCR the undertaking reports for the reporting date (standard formula, partial or full internal model)."), "unit": "EUR"},
        {**_dp("mcr_total", "Minimum Capital Requirement", "customer", "provided", provider="Your Solvency II MCR calculation (S.28)"),
         "unit": "EUR"},
        {**_dp("ri_quota_share_pct", "Reinsurance in force — quota share ceded (%)", "customer", "provided",
               provider="Your reinsurance treaties",
               note="Proportional cession of the property book. With the cat excess of loss below, it nets every insurer "
                    "loss figure; where not attested, every net figure is a named gap — no illustrative programme (E69)."), "unit": "%"},
        {**_dp("ri_xol_attachment_eur", "Reinsurance in force — catastrophe excess of loss attachment", "customer", "provided",
               provider="Your reinsurance treaties"), "unit": "EUR"},
        {**_dp("ri_xol_limit_eur", "Reinsurance in force — catastrophe excess of loss limit", "customer", "provided",
               provider="Your reinsurance treaties"), "unit": "EUR"},
        {**_dp("ri_xol_reinstatements", "Reinsurance in force — reinstatements of the cat excess of loss (number)", "customer",
               "provided", provider="Your reinsurance treaties",
               note="How many times the layer's limit can be reinstated in the year (Del. Reg. 2015/35 Art. 126(2)). Not "
                    "stated, none is assumed in the Solvency II nat-cat scenarios."), "unit": "count"},
        {**_dp("ri_xol_reinstatement_premium_eur", "Reinsurance in force — premium to reinstate the full limit once", "customer",
               "provided", provider="Your reinsurance treaties",
               note="Charged pro rata to the limit used. Not stated, no reinstatement is assumed."), "unit": "EUR"},
    ],
    "insurer_orsa_climate": [
        _dp("climate_scenarios", "Nat-cat losses and capital under a below-2 °C and a well-above-2 °C scenario, 2030-2100",
            "tellumen", "compute", provider="Tellumen nat-cat engine (NGFS scenarios, CMIP6 deltas)"),
        _dp("capital_position", "Own funds, SCR and reinsurance in force — read from your attested Solvency II figures",
            "tellumen", "compute", provider="Stated once, under Solvency II (insurer_solvency) — never stated again here"),
        _dp("orsa_narrative", "Materiality conclusion, scenario review and actions", "customer", "report", provider="You author"),
    ],
    "insurer_recovery_stress": [
        _dp("natcat_stress", "Severe nat-cat event (1-in-200 single event), today and under warming — net loss and SCR ratio",
            "tellumen", "compute", provider="Tellumen nat-cat engine"),
        _dp("capital_position", "Own funds, SCR and reinsurance in force — read from your attested Solvency II figures",
            "tellumen", "compute", provider="Stated once, under Solvency II (insurer_solvency) — never stated again here"),
        _dp("recovery_triggers", "Your SCR-ratio trigger levels and the remedial action for a breach", "customer", "report",
            provider="You author"),
        {**_dp("scr_trigger_early_warning_pct", "Recovery plan — early-warning level of the SCR ratio", "customer", "provided",
               provider="Your pre-emptive recovery plan",
               note="The SCR coverage ratio at which remedial actions are to be considered (Directive (EU) 2025/1 Art. 5(8)). "
                    "Above the SCR-breach level (100 %), which the Article sets as the minimum capital indicator."),
         "unit": "scr_ratio_%"},
        {**_dp("scr_trigger_recovery_pct", "Recovery plan — recovery-action level of the SCR ratio", "customer", "provided",
               provider="Your pre-emptive recovery plan",
               note="The SCR coverage ratio at which remedial actions are to be taken; between the early-warning level and 100 %."),
         "unit": "scr_ratio_%"},
    ],
    "eudr_dds": [
        _dp("eudr_reading", "Per-plot satellite reading of tree-cover loss after 31.12.2020 — a risk the operator weighs "
            "(Art. 10), never a verdict", "tellumen", "compute",
            provider="Tellumen (your plot geolocation + Hansen Global Forest Change)"),
        _dp("eudr_legality", "Legality evidence + supplier declarations",
            "customer", "provided", provider="Your supplier legality documentation"),
    ],
}


def catalog(framework: str) -> list[dict] | None:
    """The datapoints for a framework, each with source-category + ingestion lane + provider."""
    return CATALOG.get(framework)


def _esrs_sections() -> list[dict]:
    """The ESRS statement's figures by concept (data/reference/esrs/concepts.json): the platform computes or derives
    it, or the undertaking states it (provided values, family 'esrs'). Narratives and choices are answered items of
    the statement itself (services.governance.esrs_document), not catalog datapoints."""
    from services.governance.esrs_binding import concepts
    lanes = {"computed": ("computed", "compute"), "derived": ("computed", "compute"), "provided": ("client", "provided")}
    return [{"section": c["label"], "source": lanes[c["lane"]][0], "source_category": None, "lane": lanes[c["lane"]][1],
             "provider": "Tellumen" if c["lane"] != "provided" else "You state it (4-eyes attested)",
             "note": None, "reconcilable": False}
            for c in concepts().values() if c["lane"] in lanes and not c.get("redefined_from")]


def coverage(framework: str) -> dict | None:
    """Filing coverage DERIVED from the catalog: each datapoint's lane → a coverage bucket, plus a summary
    (how much of this filing we produce from your data). Same shape the coverage panel already consumes."""
    if framework == "esrs_pack":
        sections = _esrs_sections()
        srcs = ("computed", "integrated", "client", "out_of_scope")
        counts = {k: sum(1 for x in sections if x["source"] == k) for k in srcs}
        return {"sections": sections, "counts": counts, "total": len(sections),
                "pct_computed": round(100 * counts["computed"] / len(sections)) if sections else 0}
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
