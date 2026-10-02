"""The basis of preparation an assurance pack ships (methodology.md) and the one-line principle on its cover — one per
report family, each stating only what that family's builder does (report_snapshots._BUILDERS and the service it calls).

Every framework of services.governance.filings.FRAMEWORKS resolves to its own text; there is no default text, so a
report type without one is refused rather than described as another (E112: one ESRS text, written for the agriculture
statement, used to be shipped for every report but EUDR). A retired report's frozen snapshots get a text that says it is
retired and that its engine is gone — the pack presents the figures as filed and does not describe how they were made.
"""
from __future__ import annotations

# report type -> family. Report types of one family share one text (the SFDR product documents share their builder).
FAMILY_OF = {
    "esrs_pack": "esrs", "bank_tcfd": "bank_taxonomy", "bank_p3esg": "pillar3", "sfdr_pai": "sfdr_pai",
    "sfdr_precontractual": "sfdr_product", "sfdr_periodic": "sfdr_product", "reit_taxonomy": "nonfin_taxonomy",
    "insurer_solvency": "solvency_natcat", "insurer_orsa_climate": "orsa_climate",
    "insurer_recovery_stress": "recovery_stress", "eudr_dds": "eudr",
}

# the families whose builder reads the hazard scores under the recorded scenario and horizon
_READS_SCENARIO = {"pillar3", "nonfin_taxonomy", "solvency_natcat"}

_HOW = {
    "esrs": """1. The statement is built item by item from the version of the ESRS governing the financial year (chosen by the
   year's first day; recorded with its file's SHA-256 in `_specs`): the printed wording as captured; each datapoint through
   its concept's lane — computed by the platform, the undertaking's attested figure, or a ratio derived from them; narratives
   and choices as the undertaking answers them; anything omitted with the undertaking's stated reason (not material, the
   item's condition does not apply, or a phase-in it uses).
2. Scope: the same reporting undertaking as the financial statements — for a parent preparing consolidated statements, the
   group; the undertaking's CSRD role says whether it reports individually or for the group.
3. Computed (E1): assets and net revenue at material physical risk — the sites held at the period end, valued at finance's
   year-end figures (carrying amount, the part addressed by adaptation, the year's net revenue). A site is at material risk
   when an EU Taxonomy Appendix A climate hazard, under the high-emissions scenario over the ESRS 1 horizons, scores at or
   above the level the undertaking states (`esrs.method.physical_risk_level`, no default); the scores are those standing
   when the statement is prepared.
4. Derived: the ratios the application requirements define, in the unit they name (GHG and energy intensity per monetary
   unit of net revenue; water intensity per million EUR), from the undertaking's own figures.
5. Supporting facts for the undertaking's own figures: sites inside a listed biodiversity-sensitive area; sites in areas of
   (high) water stress by the governing version's definition (WRI Aqueduct).""",
    "bank_taxonomy": """1. The filing freezes the loan book per exposure — the facts the Annex VI templates read — with the book's count
   and total and the method record. The physical-risk engine's per-exposure scores are not frozen and not read.
2. Every template of the governing version of Delegated Regulation (EU) 2021/2178 Annex VI (recorded in `_specs`) applies
   Annex V's method. An exposure's place — in the GAR numerator, excluded from the numerator, or outside the covered assets —
   is the first leaf row of the specification whose filter it meets.
3. A general-purpose exposure to an undertaking is valued by the counterparty's own Taxonomy KPIs (turnover-based and
   CapEx-based), frozen with the filing; the CapEx-based KPI of general lending uses the counterparty's turnover KPI. A
   specific-purpose exposure, a household, a local government or a repossessed property is valued by its own stated
   Taxonomy status, objective and contribution.
4. What the Regulation says is not yet disclosed (the phase-ins the specification declares) is marked, not computed. A
   figure the loan tape holds no facts for is entered by the institution as an input cell, with the reason. The previous
   disclosure reference date (T-1) is computed from the previous period's frozen exposures.
5. The form shows the main row of the Summary of KPIs (Template 0); the annex shows every template of the governing
   version; the exports are JSON and a workbook.""",
    "pillar3": """1. The filing freezes the banking book per exposure — the facts the templates of ITS (EU) 2022/2453 (as amended by
   ITS (EU) 2024/3172; the governing version recorded in `_specs`) read — with each exposure's hazard scores, the book's
   count, scored count and total, and the method record.
2. Each exposure is located to an H3 cell and joined to the platform's per-cell hazard scores under the recorded scenario
   and horizon (sources and their maturity at freeze: `lineage.html`). Template 5 counts an exposure as sensitive to a
   chronic or an acute peril when any hazard of that category scores at or above the institution's stated at-risk level
   (`method.at_risk_level`); without a stated level that is a gap.
3. Template 1 columns i-k follow the institution's two statements, frozen with the filing: which scopes it estimates, and
   the attribution — per exposure, the gross carrying amount divided by the counterparty's total liabilities, times the
   emissions of the scopes estimated. Column k is the share of the row's gross carrying amount whose column-i emissions are
   company-reported, a gap where the source is not recorded. The narrative the instructions require is the institution's
   answer, frozen.
4. Columns filled from loan facts (maturity, IFRS 9 stage, accumulated impairment, collateral energy efficiency and the
   like) read what the institution supplies per exposure; a fact not supplied is a gap.
5. The exports are JSON and a workbook.""",
    "sfdr_pai": """1. One entity-level statement under Delegated Regulation (EU) 2022/1288 Annex I (the governing version recorded in
   `_specs`), value-weighted across every position of all the manager's funds, each counted once.
2. Every mandatory indicator of Table 1 is listed: computed, with its coverage and data source, where the inputs exist;
   otherwise marked not available with the input still required. GHG emissions and carbon footprint are financed emissions
   where the investee's EVIC is held, else the un-attributed investee total (partial); GHG intensity is the value-weighted
   intensity of the investees; the fossil-fuel indicator is the share of value in fossil-fuel sectors; indicators 5-14 are
   computed where the manager's ESG data supplies the datum for a holding, over the covered value.
3. Sovereign indicators (15-16) where the book holds sovereign exposure — country GHG excluding LULUCF divided by GDP, from
   public statistics, countries without a figure named and left out. Real-estate indicators (17-18) are marked not
   applicable where the book holds securities only, otherwise not available.
4. The EU Taxonomy lines: the turnover-based and the CapEx-based aligned KPI side by side, each value-weighted from the
   investees' own reported KPIs with its own coverage; an investee whose DNSH or minimum-safeguards attestation is false
   adds nothing to the aligned share.
5. The additional (voluntary) indicators, a per-fund coverage table, and the narrative sections (policies, actions,
   engagement, references to international standards) as the manager authors them.""",
    "sfdr_product": """1. One fund's document, filled item by item from the governing version of the Delegated Regulation (EU) 2022/1288
   template (pre-contractual Annex II / III, periodic Annex IV / V; recorded in `_specs`): each printed item is fixed wording
   as captured, computed from the fund's frozen book, or the manager's answer.
2. The filing freezes the fund, its holdings with each investee's Taxonomy KPIs, and the manager's answers — the latest
   holdings for a pre-contractual document; every position date in the calendar year to the period end for a periodic one.
3. Computed: the product's name and LEI; whether it has a sustainable investment objective (its SFDR classification); for a
   periodic document, the top investments (the fifteen largest, averaged over the position dates), the sectors with the
   fossil-fuel share, the Taxonomy-alignment graphs (each investee's own turnover / CapEx / OpEx KPIs, value-weighted, split
   into fossil gas, nuclear and the rest, with and without sovereign exposures) and the fossil gas / nuclear answer.
4. An investee whose KPIs are not on file adds nothing to the aligned share, nor does one whose DNSH or minimum-safeguards
   attestation is false; the share of value that states its KPIs is shown with the graph.""",
    "nonfin_taxonomy": """1. The filing freezes the property book: each building with its H3 cell and hazard scores under the recorded
   scenario and horizon, the exposure by hazard, the rollup and the method record. The Annex II templates of Delegated
   Regulation (EU) 2021/2178 (the governing version recorded in `_specs`) are built from it when the form is rendered.
2. Turnover is each building's gross rental revenue, or its NOI where gross revenue is not on file — a counted, disclosed
   proxy that understates turnover. Eligibility and the activity come from the Taxonomy's activity list (68.20 to 7.7
   'Acquisition and ownership of buildings').
3. Alignment per building, from activity 7.7's criteria and the building's stated facts: substantial contribution (EPC
   class or evidenced top 15 % for a building before 2021; Section 7.1 for later ones), do no significant harm to climate
   adaptation (the platform's physical-risk assessment of the building — a declared reading — and an adaptation plan), and
   minimum safeguards as the undertaking states. Aligned when all are met, not aligned when any is not, otherwise not
   known; a building not known, or under an eligibility-only phase-in, sits in neither A.1 nor A.2 and is counted on the form.
4. CapEx and OpEx are the undertaking's own ledger by activity, entered by it. The previous year (N-1) comes from the
   previous period's frozen filing.""",
    "solvency_natcat": """1. The filing freezes the underwriting book — each policy with its H3 cell and hazard scores under the recorded
   scenario and horizon, the exposure by hazard, the rollup — and the natural-catastrophe block of S.27.01.01 (ITS (EU)
   2023/894) mapped from it, with the method record. Nothing is re-run when the block is read.
2. The prescribed standard formula (Delegated Regulation (EU) 2015/35 Arts 90b, 119-126, in the version in force on the
   reporting date), region by region and peril by peril, before and after risk mitigation: specified gross losses from the
   sums insured by zone, weights and correlations of the Annexes; the scenarios' losses after the reinsurance in force; for
   risks outside Annex XIII, the undertaking's attested premiums by region — missing, the peril is marked incomplete, never
   charged on zero. Only the undertaking's attested treaty mitigates; an illustrative programme never does.
3. Beside it, labelled as context: the platform's modelled 1-in-200 (99.5 %) annual-aggregate loss on the undertaking's
   stated method, gross and net of the attested reinsurance — not an approved internal model. Without a stated method it is
   a gap; the standard formula stands on its own.
4. For a group scope the figure is the catastrophe-risk sub-module on an ownership-weighted pool of the group's policies,
   stated as such on the block: not a Title III group solvency position (no group own funds, no other SCR modules, neither
   Method 1 nor Method 2).""",
    "orsa_climate": """1. The ORSA climate change scenario analysis, item by item from the governing version of Directive 2009/138/EC
   Art. 45a and 51(1b)(e) as inserted by Directive (EU) 2025/2 (recorded in `_specs`), for the undertaking or group the
   report is for: the printed wording as captured, the items the platform computes, and the undertaking's answers. The
   report's planned date chooses the rules and is frozen with it.
2. Computed: the quantified exposure (sum insured at high hazard; each scenario's modelled change in expected loss and in
   the net 1-in-200 loss against the attested own funds); the two long-term scenarios (below and above 2 °C, chosen by the
   undertaking's switches) with their pathway and warming; and each scenario at 2030, 2050 and 2100 against today —
   expected annual loss, technical premium, net 1-in-200 annual loss, and the SCR ratio if that change were added to the SCR
   undiversified (declared reading 'Capital impact').
3. Every run is on the same book with its accumulation zones held fixed, the attested reinsurance and the attested capital
   of the undertaking the filing is for.
4. The materiality conclusion, the review, the interval, the derogation for small and non-complex undertakings (under which
   the scenario items are not required) and the SFCR statement are the undertaking's answers.""",
    "recovery_stress": """1. The pre-emptive recovery plan's natural-catastrophe stress and capital indicators, item by item from the
   governing version of Directive (EU) 2025/1 Art. 5(7) and (8) (recorded in `_specs`), for the undertaking or group the
   report is for: the printed wording as captured, the items the platform computes, and the undertaking's answers. The
   report's planned date chooses the rules and is frozen with it.
2. Computed: a severe natural-catastrophe event — the 1-in-200 single event and the 1-in-200 year, net of the attested
   reinsurance — today and under the undertaking's well-above-2 °C scenario at the nearest horizon, taken from the attested
   own funds: own funds after the loss, the SCR ratio, whether it breaches the SCR, and which of the plan's trigger levels
   it crosses (declared reading 'SCR after the event').
3. The capital indicators: the SCR-breach indicator (100 %) and the undertaking's own attested early-warning and recovery
   levels, against today's ratio and each stress.
4. The other macroeconomic and financial scenarios, the qualitative indicators, the monitoring arrangements and the remedial
   action on a breach are the undertaking's answers.""",
}

_NOT = {
    "esrs": "The ESRS standards other than E1, E3 and E4. The platform computes no GHG emissions: the E1 emission figures are "
            "the undertaking's own attested figures, from which it derives the intensity ratios.",
    "bank_taxonomy": "Physical-risk, financed-emission and credit-risk analytics — filings frozen before 2026-10-01 carry them, "
                     "marked as the earlier report shape. No XBRL: no official XBRL binding of the Annex VI templates is held.",
    "pillar3": "What no template prints is not frozen: modelled physical-climate expected loss (Templates 1 and 5 print the "
               "institution's accumulated impairment), counterparty transition expected loss, collateral EPC stranding, value "
               "exposed per hazard, a value-weighted Taxonomy summary (Templates 6-9 print the GAR and BTAR) and a book-level "
               "value at risk. The EVIC-based PCAF figure is not a Template 1 attribution. No XBRL: an XBRL export is refused — no "
               "official binding of the templates is held. A filing frozen under an earlier report shape keeps what it "
               "froze; its form marks those parts as from the earlier shape.",
    "sfdr_pai": "No physical-hazard scoring. Prior-year comparison and look-through are reported per fund, not in the entity "
                "statement.",
    "sfdr_product": "No physical-hazard scoring. Items the specification leaves to the manager are its answers, not computed.",
    "nonfin_taxonomy": "Modelled losses are not part of the Taxonomy KPIs; the hazard scores enter only through the climate risk "
                       "and vulnerability assessment of the adaptation criterion.",
    "solvency_natcat": "The other Basic SCR modules and own funds: this filing reports the natural-catastrophe part of "
                       "S.27.01.01 only.",
    "orsa_climate": "The rest of the ORSA: this filing is its climate change scenario analysis only.",
    "recovery_stress": "The rest of the recovery plan: this filing is its natural-catastrophe stress and capital indicators only.",
}

_PRINCIPLE = {
    "esrs": "Every datapoint is computed by the platform, attested by the undertaking, derived from those, or omitted with the "
            "undertaking's stated reason; nothing is filled by assumption.",
    "bank_taxonomy": "A cell no exposure states the fact for is blank, never zero; where a counterparty's KPIs are not on file "
                     "the cell is blank, never estimated.",
    "pillar3": "Every printed cell is computed from the frozen book, the stated at-risk level and the institution's statements, "
               "or is a fact the institution supplies; a fact not stated is a gap, never a number.",
    "sfdr_pai": "An indicator is computed only where its inputs exist; otherwise it is marked not available with the input "
                "required, never a silent zero.",
    "sfdr_product": "An investee whose Taxonomy KPIs are not on file is never assumed aligned; the share of value that states "
                    "them is shown.",
    "nonfin_taxonomy": "Each criterion is met, not met or not known from the building's stated facts, never guessed; a "
                       "building not known is in neither A.1 nor A.2.",
    "solvency_natcat": "The standard formula follows the Articles on the attested inputs; only an attested treaty mitigates; a "
                       "missing input marks the peril incomplete, never charged on zero.",
    "orsa_climate": "The computed items run on the attested capital and reinsurance; everything else is the undertaking's "
                    "answer.",
    "recovery_stress": "The stress runs on the attested own funds, reinsurance and trigger levels; everything else is the "
                       "undertaking's answer.",
    "eudr": "Plot readings show what the satellite data shows, a risk the operator's assessment weighs, never a verdict.",
}

_CONTROLS = """## Controls over the figures
- The figures are frozen as an immutable, versioned snapshot; its SHA-256 is recomputed whenever it is read (`manifest.json`
  says whether it still matches). A correction is a new version.
- The snapshot records what produced it: the specification version governing each family, with its file's SHA-256 and
  sign-off (`_specs`); the engine and code versions and the feed freshness at freeze (`lineage.html`); the presentation
  currency and every rate used (`_fx`); the consolidation rule where the book is weighted (`_consolidation`); and the values
  provided and attested under four eyes (`_provided_attested`).
- The filing moves from draft through review, approval and attestation to submission: review raises a four-eyes approval
  that a different person decides (the database refuses the maker as checker), and a named person attests the frozen
  figures before submission.
- The approval decisions are in `approvals_4eyes.json`; the access audit log in `audit_trail.json`."""

_EUDR = """## What the statement rests on
1. The undertaking's status (size class, address, EORI) on the shipment's date — stated, and approved by a second person.
2. The plots of land the product was produced on, with their geolocation (Art. 2(28)), and for each the satellite reading
   of tree-cover loss after 31 December 2020 — what the dataset shows, a risk the assessment weighs (Art. 10), never a verdict.
3. The supplier (Art. 9(1)(e)), the legality evidence (Art. 9(1)(h)) and the risk assessment (Art. 10-13), approved by a
   second person.
4. The checks every statement passes before it can be prepared, each with its article, frozen with it.

## Controls
- Four eyes on the status, the risk assessment and the statement; attestation before submission.
- The statement is frozen as an immutable, versioned snapshot; an amendment is a new statement that supersedes it."""


def _framework(report_type: str) -> dict:
    from services.governance.filings import FRAMEWORKS
    if report_type not in FRAMEWORKS:
        raise ValueError(f"no basis of preparation for unknown report type '{report_type}'")
    return FRAMEWORKS[report_type]


def principle(report_type: str) -> str:
    """The one line the pack's cover states about what this report's figures rest on."""
    fw = _framework(report_type)
    if fw.get("retired"):
        return "This report type is retired; the figures are presented exactly as frozen."
    return _PRINCIPLE[FAMILY_OF[report_type]]


def methodology(report_type: str, *, version, entity: str, basis_text: str, period_end, generated: str,
                contents: str) -> str:
    """methodology.md for a snapshot of this report type — its own framework, its own builder, nothing else. basis_text is
    the reporting basis as recorded; a report that reads neither the scenario nor the at-risk level on it is described by
    its period alone."""
    fw = _framework(report_type)
    family = FAMILY_OF.get(report_type)
    if family is not None and family != "eudr" and family not in _READS_SCENARIO and not fw.get("retired"):
        basis_text = f"period ending {period_end}"
    head = (f"# Basis of preparation\n\n## What this pack is\nThe evidence behind **{fw['label']}** ({fw['basis']}), frozen in "
            f"snapshot **{report_type} v{version}** of **{entity}**: {basis_text}. Generated {generated} (UTC).\n\n")
    tail = f"\n\n## Contents of this pack\n{contents}\n"
    ret = fw.get("retired")
    if ret:
        succ = f" It is replaced by `{ret['replaced_by']}`." if ret.get("replaced_by") else ""
        return head + (f"## This report type is retired\nRetired since {ret['since']}: {ret['reason']}.{succ} The engine that "
                       "produced this snapshot is no longer in the platform, so this pack does not describe how its figures "
                       "were made: it presents them exactly as frozen, with the hash, the engine versions recorded at freeze "
                       "and the control evidence.\n\n") + _CONTROLS + tail
    if family == "eudr":
        return head + _EUDR + tail
    scen = ("The hazard scores are read under the scenario and horizon recorded on the reporting basis."
            if family in _READS_SCENARIO else
            "The scenario and horizon recorded on the reporting basis are the organisation's settings at freeze; this "
            "report's figures do not read them.")
    return (head + f"## How the figures are produced\n{_HOW[family]}\n\n{scen}\n\n## What is not in this filing\n"
            f"{_NOT[family]}\n\n" + _CONTROLS + tail)
