# Official form mapping — what each regulation actually requires vs. what Tellumen assembles

**Purpose.** For every framework we file, this maps the **official regulatory template** (its exact structure,
per the legal text) to **what our assembled "Official form" renders today**, states the **gap**, and names
**what to build** to reach the exact template — with an honest note on whether our data supports it or the
customer must supply it.

**Honest headline.** Our assembled form is **datapoint-faithful** for SFDR, ESRS and EUDR (we render the
regulation's own indicators/datapoints in its own groupings). For the two **bank quantitative matrices**
(EBA Pillar 3 Template 5, and the full EU-Taxonomy GAR template set) we currently render a **readable,
engine-driven summary** of the right metrics — not the exact multi-axis regulatory grid. Those two are the
real build targets. The in-app form is always a **preparation aid**; the authoritative filing is still made
on the regulator's own system/taxonomy (iXBRL for ESRS, supervisory reporting for Pillar 3, TRACES for EUDR).

Links: `services/governance/reg_reference.py` now points `url` at the guaranteed-English EUR-Lex (CELEX) act
and `form_url` at the actual **template** document (distinct from the act where the templates live in a
separate amending act / annex / regulator page).

---

## 1. Bank — EU Taxonomy Article 8 (GAR) + TCFD  ·  `bank_tcfd`
**Official template.** Disclosures Delegated Act **(EU) 2021/2178**, **Annexes V–XI** (credit-institution KPIs,
applying from 2024): the Green Asset Ratio template set — GAR **by environmental objective**,
**stock vs. flow**, **turnover- and CapEx-based** KPIs, plus KPIs for **specialised lending / trading book /
fees & commissions**, and the **Annex XI qualitative** narrative. Numerator = Taxonomy-aligned exposures;
denominator = covered assets; several templates split by objective and by transitional/enabling activity.
**Our form today.** One "GAR (summary)" table: Taxonomy-**eligible** / not-eligible / not-assessed / total
covered assets (€ and % of covered), plus PCAF financed emissions and a TCFD physical-risk metrics block.
**Gap.** We show **eligibility** (the honest computable leg) as a single summary, not the full multi-template
GAR grid, and not **alignment** (numerator) — alignment needs DNSH + minimum-safeguards flags the customer
determines (already surfaced as `integrated`). 
**Build.** (a) Render the GAR as the real template axes we *can* populate: eligible/aligned/of-which-transitional/
enabling, **by environmental objective**, stock basis. (b) Keep alignment cells as customer-provided (Lane 2).
(c) Add the Annex XI qualitative section as author-on-form. Data: eligibility computed; alignment = customer.

## 2. Bank — Pillar 3 ESG risks  ·  `bank_p3esg`
**Official template.** ITS **(EU) 2022/2453**, **Annex I** (templates) + **Annex II** (instructions):
- **Template 1** transition risk — exposures by **NACE sector** towards carbon-related assets, maturity buckets.
- **Template 2** loans collateralised by real estate — **EPC-band** distribution.
- **Template 3** alignment metrics / Scope-3 emissions.
- **Template 4** exposures to top-20 carbon-intensive firms.
- **Template 5** **physical risk** — exposures by **NACE sector (rows)** × **maturity bucket** (≤5y, 5–10y,
  10–20y, >20y, avg. weighted maturity) × **chronic / acute / chronic+acute** climate-event sensitivity, with
  *of which* Stage-2, non-performing, accumulated impairment, and *of which sensitive to physical-risk events*.
- **Templates 6–8** GAR/BTAR; **Templates 9–10** mitigating actions.
**Our form today.** "Template 5" as **value-at-risk by hazard** (€) + *of which chronic & acute by hazard*;
a GAR eligibility summary; a Scope-1/2/3 transition block.
**Gap.** Real Template 5 is a **sector × maturity × chronic/acute matrix**, not a by-hazard list; we don't yet
emit Templates 1/2/4 or the maturity/credit-quality "of which" columns.
**Build (priority).** Re-shape Template 5 to the official grid: **rows = NACE sector** (from `portfolio_entities.nace_code`),
**columns = maturity bucket × {chronic, acute, both}** exposure (€), *of which physical-risk-sensitive* = our
High+ engine output. We hold counterparty NACE, outstanding balance, maturity and the hazard scores — so this
matrix is **computable from our data** (chronic = drought/heat/soil-water/coastal-SLR; acute = flood/storm/
wildfire/coastal surge). Template 2 needs EPC bands (customer/EPC feed); Template 4 needs issuer emissions.

## 3. REIT — Taxonomy Article 8 + TCFD  ·  `reit_tcfd`
**Official template.** 2021/2178 **Annexes I–II** — turnover / CapEx / OpEx Taxonomy KPIs for non-financial
undertakings (real-estate activities), plus the qualitative Annex.
**Our form today.** Taxonomy eligibility summary + NOI-impact + physical-risk metrics.
**Gap / build.** Same pattern as §1 but the **non-financial** three-KPI (turnover/CapEx/OpEx) template rather
than the GAR. Buildable for eligibility; alignment = customer.

## 4. Asset manager — SFDR PAI  ·  `sfdr_pai`   ✅ faithful
**Official template.** RTS **(EU) 2022/1288**, **Annex I** — the PAI statement. **Table 1** = the **14 mandatory**
indicators grouped by theme (GHG emissions, biodiversity, water, waste, social & employee), columns:
*Adverse-impact indicator · Metric · Impact year n · Impact year n-1 · Explanation · Actions taken/planned*.
**Tables 2–3** = additional climate / other indicators (at least one each).
**Our form today.** Table 1 rendered in the Annex's own themed subgroups with the 14 indicators + values;
Tables 2–3 for the selected additional indicators; the Explanation / Actions narrative columns are noted as
completed at submission.
**Gap.** Minor — the **year n-1 comparative** column and the narrative columns are not yet stored; otherwise
structurally faithful. **Build:** add the prior-period column + persist the two narrative columns.

## 5. Agri / manufacturer — ESRS E1 (+ E3/E4)  ·  `csrd_e1` / `esrs_pack`   ✅ datapoint-faithful
**Official template.** ESRS Delegated Reg. **(EU) 2023/2772**, **Annex I** — E1 Climate (E1-1…E1-9: transition
plan, policies, targets, energy, **Scope 1/2/3 GHG**, GHG intensity, **financial effects** of physical & transition
risk), E3 Water, E4 Biodiversity — each a set of **disclosure requirements + datapoints**, tagged in the **EFRAG
ESRS XBRL taxonomy** (there is no single fixed "grid": it's the datapoint set + iXBRL tags).
**Our form today.** The reported datapoints grouped by disclosure requirement; iXBRL/ESEF shaping exists
(`build_ixbrl`), bound provisionally until the adopted EFRAG element map is dropped in.
**Gap.** Datapoint-faithful; the only external gap is the **adopted taxonomy element map** (one JSON file) for
a validated ESEF filing. **Build:** none structural — drop in `config/efrag_esrs_binding.json` when final.

## 6. Insurer — climate / NatCat (Solvency II / IFRS S2)  ·  `insurer_climate`
**Official template.** No single EU quantitative template. Governed by **Solvency II** climate-risk supervision
and **IFRS S2** (industry-based guidance for insurance) — sums insured / exposure / expected loss by peril &
geography, cross-referenced to the ORSA. (EIOPA collects NatCat exposure through supervisory reporting.)
**Our form today.** Sum insured / EAL / loss-ratio by peril & geography.
**Gap / build.** Structurally reasonable; align section headings to the **IFRS S2** industry metric taxonomy and
add the ORSA cross-reference as author-on-form.

## 7. EUDR — Due Diligence Statement  ·  `eudr_dds`   ✅ faithful
**Official template.** Regulation **(EU) 2023/1115**, **Art. 33** + **Annex II** — the DDS content: operator,
commodity/HS code, quantity, country of production, **geolocation of all plots** (polygons/points), and the
deforestation-free + legality conclusion; submitted to **TRACES**.
**Our form today.** `assemble_dds()` builds the DDS from plot polygons + satellite forest-loss determinations;
`traces_client.build_submission()` maps it to a TRACES-shaped envelope (prepared mode; live via config).
**Gap.** Field-name alignment to the published TRACES/EUDR-IS schema (flagged in every response) + operator
registration (customer). **Build:** confirm the mapping against the sandbox when credentials land.

---

## Build priority (highest regulatory value first)
1. **Pillar 3 Template 5** as the real NACE × maturity × chronic/acute matrix — fully computable from our data.
2. **Taxonomy GAR** by-environmental-objective template (eligibility computed, alignment customer-provided).
3. **SFDR** prior-period column + persisted narrative columns.
4. REIT turnover/CapEx/OpEx Taxonomy template; insurer IFRS S2 headings; ESRS taxonomy element map (external).

Everything above keeps the standing honesty rules: computed cells are labelled `book`/`calc`, customer-provided
cells stay `integrated` (never fabricated), and the in-app form is a preparation aid — the binding filing is
made on the regulator's own system.
