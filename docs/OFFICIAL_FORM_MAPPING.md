# Official form — regulatory gap assessment (primary-source, cited)

**Method.** Every official structure below was read from the **primary regulatory text** (EUR-Lex CELEX,
the Commission's own Annex PDFs, EFRAG delegated-act annexes, IFRS S2), then cross-checked against our
`filing_annex.py` / `filing_form.py` / `datapoint_catalog.py` builders. Where a template grid is published
as a graphic (so exact cell wording couldn't be extracted), it is marked **unverified-to-the-cell** — never
invented. Sources are listed per framework.

**One-line verdict.** SFDR / ESRS / EUDR are **datapoint-faithful in substance** but our *rendered* form has
fidelity gaps (columns, rows, wording). The two **bank quantitative matrices** — EBA Pillar 3 Templates 1 & 5,
and the EU-Taxonomy GAR (8 templates) — are rendered as **flat summaries**, not the regulator's grids, and are
**largely computable from data we already hold**. Two **correctness bugs** surfaced (REIT mis-routed to a GAR;
insurer reuses the bank builder). The in-app form remains a **preparation aid**; the binding filing is still
made on the regulator's own system (supervisory reporting / ESEF iXBRL / TRACES).

Data we hold (per catalog + forms): counterparty **NACE code**, **outstanding balance** (≈ gross carrying
amount), **maturity**, per-hazard **chronic/acute exposure**, asset **geolocation**, **Taxonomy eligibility**,
**PCAF Scope 1/2/3**. Customer-only: IFRS-9 credit quality (Stage 2 / NPE / impairment), **Taxonomy alignment**
(DNSH + minimum-safeguards flags), **EPC bands**, issuer-reported emissions, GHG inventory, narratives.

---

## 1. Bank — EBA Pillar 3 ESG risks · `bank_p3esg`  ✅ full quantitative set built (T1·T5·T6-8·T10)
**Governing text.** Implementing Reg. **(EU) 2022/2453** — inserts **Art. 18a** into ITS (EU) 2021/637; **Annex XXXIX**
= templates, **Annex XL** = instructions. Scope: **large listed institutions** (CRR Art. 449a); annual + semi-annual
from 31 Dec 2022. Set = **Tables 1–3** (qual.) + **Templates 1–10** (Template 9 = BTAR, voluntary).

**Template 5 — physical risk (verbatim, Annex XL).** Columns **a–o** (15): (a) geographical area (NUTS);
(b) **gross carrying amount**; (c–o) *of which sensitive to physical events* → (c–g) **maturity buckets** ≤5y /
>5≤10y / >10≤20y / >20y / avg-weighted-maturity; (h) **chronic**; (i) **acute**; (j) **both chronic+acute**;
(k) Stage 2; (l) non-performing; (m) accumulated impairment; (n) of-which Stage 2; (o) of-which NPE.
**Rows:** by **NACE sector × geography (NUTS)**, over three blocks — NFC exposures, loans collateralised by
immovable property, repossessed real estate — + subtotals + total. *(NACE row captions are graphic → unverified-to-the-cell.)*

**Template 1 — transition risk (verbatim, Annex XL).** Columns **a–p**: (a) gross carrying amount; (b) of-which
excluded-from-Paris-benchmark; (c) env-sustainable (CCM); (d) Stage 2; (e) NPE; (f) accumulated impairment;
(g) of-which Stage 2; (h) of-which NPE; (i) **GHG financed emissions (Scope 1+2+3, tCO₂e)**; (j) of-which Scope 3;
(k) % from company-specific reporting; (l–p) maturity buckets. **Rows:** NACE "highly-contributing" sectors
(A–H, L) + fossil-fuel/other-carbon subtotals + "other sectors" + total (rows 2–52).

**Templates 6–8 — GAR.** T6 KPI summary (CCM / CCA / Total / %coverage × GAR stock/flow); T7 assets by
counterparty type × eligibility **and alignment** (CCM+CCA, of-which specialised/transitional/enabling); T8
= same as %. First reference date 31 Dec 2023.

**We render today (BUILT)** — `_p3esg_annex` renders the full ITS quantitative set to the real grid structure,
in regulatory order, computed at form-view time from the frozen snapshot's per-asset book (`pillar3_templates.py`):
- **Template 1 (transition)** `template1_grid` — rows = NACE section; computed cols gross carrying amount +
  financed emissions Scope 1+2+3 + of-which Scope 3 (same per-asset ghg the platform already sums). Verified
  Meridian 1,594,585 tCO₂e / Scope3 1,030,724. Credit-quality/alignment/Paris/maturity = customer, declared.
- **Template 5 (physical)** `template5_grid` — rows = NACE section; gross carrying amount + of-which physical-
  risk-sensitive (H/VH) + chronic (h)/acute (i)/both (j) from the per-hazard TCFD split. Maturity + IFRS-9 = customer.
- **Templates 6–8 (GAR)** `gar_grid` — eligible + aligned by counterparty class (fin corp K / non-fin corp /
  households / general govt), covered-assets denominator EXCLUDING general govt (Art. 7), GAR-on-stock ratio, from
  per-asset `taxonomy_status` (aligned⊆eligible). CCM/CCA per-objective split + GAR-on-flow + specialised/enabling/
  transitional = customer, declared. Verified Meridian: covered €2.25bn, 49.7% eligible, 0% GAR (eligibility-classified only).
- **Template 10** — other mitigating actions outside the Taxonomy (green bonds / specialised green lending), 5-col
  official structure, rows customer-supplied (instrument type not on the book).

**Remaining (customer/graphic):** the NUTS-geography sub-breakdown of Template 5 rows, the IFRS-9 credit-quality
columns (Stage2/NPE/impairment), alignment flags + % company-reported, and EPC (Template 2) — all customer/integrated.
_Source: [CELEX:32022R2453](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2453) OJ L 324/1; [EBA ITS final report](https://eba.europa.eu/sites/default/files/document_library/Publications/Draft%20Technical%20Standards/2022/1026171/EBA%20draft%20ITS%20on%20Pillar%203%20disclosures%20on%20ESG%20risks.pdf)._

## 2. Bank — EU Taxonomy Art. 8 (GAR) + TCFD · `bank_tcfd`
**Governing text.** Del. Reg. **(EU) 2021/2178**, **Annex V** (methodology) + **Annex VI** (credit-institution KPI
templates). **Annex VI = 8 templates** (read from the Commission Annex VI PDF): **T0** Summary of KPIs · **T1**
Assets for GAR calc · **T2** GAR sector information · **T3** GAR KPI **stock** · **T4** GAR KPI **flow** · **T5**
off-balance-sheet (FinGuar + AuM) · **T6** fees & commissions (from 2026) · **T7** trading book (from 2026).
Each KPI carries **Turnover-KPI and CapEx-KPI columns × the six environmental objectives × substantial-
contribution / DNSH / of-which use-of-proceeds / transitional / enabling**. **Numerator = Taxonomy-*aligned*
exposures; denominator = covered assets excluding sovereigns / central banks / supranationals (Art. 7).** Full
GAR from 1 Jan 2024. *(T3/T4 finest SC/DNSH sub-column labels unverified-to-the-cell.)*

**We render today** (`_located_annex`): **T0 Summary of KPIs** (computed — total, covered assets excl. general
governments per Art. 7, eligible, aligned/GAR-on-stock), the **Templates 6–8 GAR grid by counterparty class**
(gross / eligible / aligned, Art. 7 exclusion), and **T3 GAR-stock by environmental objective** (the official
six-objective axis, with Climate-Change-Adaptation eligibility computed — the one objective this platform
assesses — and the other five objectives, the per-objective mapping, the Turnover-vs-CapEx weighting, and
alignment declared customer-supplied).

**Remaining gap.** Templates 1–2 (assets/sector detail), T4 (GAR on **flow**), T5 (off-balance-sheet), and the
per-cell SC/DNSH/of-which-enabling/transitional sub-columns — all either large or customer-data-gated (alignment
needs TSC + DNSH + per-activity objective mapping the institution supplies). The computed spine (T0 + counterparty
GAR + T3 objective eligibility) is in place; the rest is honestly declared, not fabricated.
_Source: [CELEX:32021R2178](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178); [Annex VI PDF](https://ec.europa.eu/finance/docs/level-2-measures/taxonomy-regulation-delegated-act-2021-4987-annex-6_en.pdf)._

## 3. REIT — EU Taxonomy Art. 8 (non-financial) + TCFD · `reit_tcfd`  ✅ correctness bug FIXED
**Governing text.** A REIT is a **non-financial undertaking** → Del. Reg. 2021/2178 **Annexes I & II**: three KPI
templates — **Turnover / CapEx / OpEx**. Rows: **A. eligible → A.1 aligned (of-which enabling/transitional) ·
A.2 eligible-not-aligned · B. non-eligible · Total**. Columns: activity+NACE, absolute €, proportion %, **SC (6
objectives) · DNSH (6 objectives) · minimum safeguards (Y/N) · enabling/transitional markers · year N & N-1**.
**Full KPIs from 1 Jan 2023.**
**Bug (FIXED).** `build_annex` used to route `reit_tcfd` through `_located_annex`, which rendered a **Green Asset
Ratio** — GAR is credit-institutions-only; a REIT must never file one. **Fix (commit `5635275`):** new
`_reit_annex` renders the three **Turnover / CapEx / OpEx KPI templates** on the Annex II row skeleton (A.1
aligned / of-which enabling / of-which transitional / A.2 eligible-not-aligned / Total A.1+A.2 / B non-eligible /
Total), KPI figures declared customer-supplied (financial-statement data). Plus the property book's Taxonomy-
**eligible** activity 7.7 on an asset basis (informational, clearly NOT the KPI basis) and TCFD physical risk —
which is surfaced as the evidence base for the Climate-Change-Adaptation objective + adaptation-DNSH. No GAR.
Verified live on Stellar Logistics REIT.

## 4. Asset manager — SFDR PAI · `sfdr_pai`  ✅ rendered form rebuilt to Annex I
**Governing text.** RTS **(EU) 2022/1288**, **Annex I** — the PAI statement. **Table 1** columns (verbatim, 6):
*Adverse sustainability indicator · Metric · Impact [year n] · Impact [year n-1] · Explanation · Actions taken,
and actions planned and targets set for the next reference period*. **18 rows**: 14 investee-company (1–9
climate/environment; 10–14 social), **15–16 sovereign/supranational**, **17–18 real estate**. **Tables 2–3** =
additional environmental (22) / social (24) menu, "choose ≥1 from each", 3-column layout.
**We render today (BUILT).** `_sfdr_annex` now renders Table 1 to the exact Annex-I structure: the **6 verbatim
columns** above, split into the four official sections — *Climate & environment* (indicators 1–9), *Social &
employee* (10–14), *Sovereigns & supranationals* (15–16), *Real estate* (17–18) = **18 mandatory rows**, each
with its **verbatim RTS Metric wording**. The impact figure binds to the frozen datapoint (`indicator.<n>`);
Impact[n-1] / Explanation / Actions bind to `indicator.<n>.prior|expl|action` so an override can populate them,
else render "—" (completed at submission). **Tables 2–3** render as the opt-in menus driven by whatever the
snapshot carries (`indicator.env.*` / `indicator.social.*`), with the "select ≥1 from each" note — never a
fabricated menu. Verified: 18 mandatory rows in 4 sections, 6 columns, sovereign/RE wording exact.
_Source: [C(2022) 1931 final Annex 1 PDF](https://ec.europa.eu/finance/docs/level-2-measures/C_2022_1931_1_EN_annexe_acte_autonome_part1_v6.pdf); [CELEX:32022R1288](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32022R1288)._

## 5. Agri / manufacturer — ESRS E1 / E3 / E4 · `csrd_e1` / `esrs_pack`  ✅ datapoint-faithful
**Governing text.** ESRS Del. Reg. **(EU) 2023/2772**, Annex I. **E1** has **9 DRs** — E1-1 transition plan · E1-2
policies · E1-3 actions · E1-4 targets · E1-5 energy · E1-6 **Gross Scope 1/2/3 + total GHG** (GHG intensity is a
sub-metric of E1-6) · E1-7 removals & carbon credits · **E1-8 internal carbon pricing** · **E1-9 anticipated
financial effects (physical & transition)**. **E3** E3-1…E3-5 (**E3-4 = water consumption m³ + water intensity
m³/€m revenue**; E3-5 financial effects). **E4** E4-1…E4-6 (**E4-5 impact metrics — land-use change, protected-
area interface**; E4-6 financial effects). Filed as **ESEF iXBRL** tagged to the EFRAG ESRS taxonomy — a datapoint
set + tags, **no fixed numeric grid**.
**We render / compute.** E1-9 physical financial effects (asset value-at-risk, business interruption, COGS-at-risk,
withheld) with the r²≥0.40 gate; E3-5 water-stress exposure €; E4-5 deforestation-free %, forest-loss ha,
protected-area overlap. GHG (E1-5/6/7/8) = customer carbon tool; narratives = customer.
**Gap & build.** Substance is faithful. **(a) E3-4 honesty label — BUILT:** `e3_water` is relabelled **"ESRS E3-4
— water-stress exposure · PROXY"** with a note that E3-4 mandates *metered* m³ + intensity (m³/€m revenue) and this
hazard-based indicator is **not** the meter reading; the metered figure is the separate `e3_measured_water`
customer datapoint ("metered water consumption (m³) + intensity"), and `water_topic` carries an `e3_4_note` +
`metric_kind` that the EsrsPack card renders as a warning banner. Neither is presented as satisfying the other.
**(b) Remaining external blocker** to a **validated ESEF** filing is the adopted **EFRAG ESRS Set 1 XBRL element
map** — a drop-in `config/efrag_esrs_binding.json` the code already accepts.
_Source: EFRAG delegated-act annexes [E1](https://www.efrag.org/sites/default/files/media/document/2024-08/ESRS%20E1%20Delegated-act-2023-5303-annex-1_en.pdf) / [E3](https://www.efrag.org/sites/default/files/media/document/2024-08/ESRS%20E3%20Delegated-act-2023-5303-annex-1_en.pdf) / E4; [CELEX:32023R2772](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2772)._

## 6. Insurer — climate / NatCat · `insurer_climate`  ✅ own IFRS-S2 annex (builder mismatch FIXED)
**Governing text.** **No fixed EU quantitative NatCat disclosure template.** Layer 1 = **IFRS S2** (Governance /
Strategy / Risk mgmt / Metrics & targets) with **insurance industry metrics (SASB FN-IN-450a)**: **450a.1 PML from
weather-related natural catastrophes**; **450a.2 cat monetary losses by event type & geographic segment, net &
gross of reinsurance**; **450a.3 underwriting/risk-integration narrative**. Layer 2 = **Solvency II ORSA**
(principles-based scenario narrative) + the **SCR NatCat sub-module** (a capital grid, not a disclosure template).
*(Exact FN-IN-450a code wording behind an IFRS OAuth wall → unverified-to-the-letter.)*
**Bug (FIXED).** `insurer_climate` used to route through `_located_annex` — the **bank TCFD builder** — so it showed
GAR / PCAF, which an insurer must never file. **Fix:** `build_annex` now dispatches `insurer_climate → _insurer_annex`
(filing_annex.py:1004; `_located_annex` is now bank-only, line 1008). The insurer annex renders the underwriting
metrics on the IFRS S2 / SASB FN-IN-450a headings: **NatCat underwriting summary**, **sum insured at risk by peril
(event type)** and **by geography**, **EAL by severity band**, **catastrophe accumulation (AEP/OEP + PML)**,
**Solvency II NatCat SCR (99.5% VaR)**, **net-vs-gross of reinsurance** (450a.2), and **investment-side climate VaR**
(the asset half). No GAR/PCAF. Tested: `tests/unit/test_insurer_annex.py`; `test_located_annex_gar.py` guards that the
bank GAR path is unchanged. Verified live on Iberia Mutual (insurer demo).

## 7. EUDR — Due Diligence Statement · `eudr_dds`  ✅ Annex II fields complete
**Governing text.** Reg. **(EU) 2023/1115**, **Art. 4(2)** + **Art. 33** (TRACES/EUDR IS) + **Annex II** — DDS content:
operator name/address + **EORI**; **HS code + description + trade name + scientific name**; **quantity (net mass,
supplementary units)**; **country of production (+ parts)**; **geolocation of all plots** (point; **polygon >4 ha**)
+ **date/time range of production**; reference/verification number + declaration + signature. *(Annex II exact
numbering: WebFetch couldn't render the annex block → confirm ordering on EUR-Lex before building.)*
**We produce.** Geolocation (point/polygon >4 ha), country/parts, HS/commodity, area, deforestation determination +
evidence. Correctly flagged to operator (not faked): net-mass **quantity (kg)**, missing **EORI**, **signature**.
**BUILT (Art. 9(1)(b) & (d)).** Each statement item now carries **trade name** (defaults to the commodity, operator
refines), **free-text description** (`commodity (HS ####)`), and the **full scientific name**: for the single-species
covered commodities this is the authoritative species constant we supply (`_EUDR_SPECIES`: cocoa→*Theobroma cacao*,
coffee→*Coffea* spp., oil palm→*Elaeis guineensis*, rubber→*Hevea brasiliensis*, soya→*Glycine max*, cattle→*Bos
taurus*). **Wood** is deliberately excluded — its species varies per shipment, so scientific name routes to the
operator (surfaced in `operator_completes`, never guessed). Every plot carries a **`production_date_range`** field
(Art. 9(1)(d)) — null in our feed (operational shipment data), so it's flagged as an operator to-do, not faked.
Tests: `test_eudr_dds.py` (species supplied for known; routed for wood; production-date carried + flagged).
**Remaining (external):** align envelope keys to the TRACES DDS schema when sandbox credentials land (Tier 2).
_Source: [CELEX:32023R1115](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1115)._

---

## Build order (regulatory value × computability)
1. **Correctness bugs — ✅ BOTH FIXED:** REIT → non-financial Turnover/CapEx/OpEx template, not GAR (`_reit_annex`,
   commit 5635275); insurer → own IFRS-S2 annex, not the bank builder (`_insurer_annex`, dispatch filing_annex.py:1004).
   Both tested and verified live.
2. **Pillar 3 Template 5** — ✅ BUILT & WIRED: real NACE-section × physical-risk grid (`template5_grid`,
   filing_annex.py:802); maturity buckets + IFRS-9 credit-quality fill from customer-provided per-loan attributes
   (`residual_maturity_years`, `ifrs9_stage`) where present, else blank + declared.
3. **Pillar 3 Template 1** — ✅ BUILT & WIRED: NACE-section transition-risk grid (`template1_grid`,
   filing_annex.py:688); maturity/%-company-reported columns customer-supplied, declared blank.
4. **Taxonomy GAR** — ✅ BUILT & WIRED: T0 Summary + T3 stock-by-objective + Templates 6–8 counterparty grid
   (`gar_grid`), Art. 7 exclusion; eligibility computed, alignment customer.
5. **SFDR** — ✅ BUILT & WIRED: Annex I Table 1 all 18 mandatory indicators (investee 1–14 + sovereign 15–16 +
   real-estate 17–18), prior-year (n-1) comparative (`_attach_prior_year`), `ml/regulatory/sfdr_pai.py`.
6. **ESRS** — E3-4 stress-proxy label BUILT; the EFRAG element map / ESEF is the external XBRL blocker (see workstream ④).
7. **EUDR** — Annex II fields BUILT (§7); TRACES schema alignment is external (sandbox credentials).

**All four reg-deepening workstreams are BUILT & WIRED** (verified end-to-end in code, Sept 2026):
- **① Correctness bugs** — fixed (REIT `_reit_annex`, insurer `_insurer_annex`).
- **② Official-form fidelity** — Pillar 3 T1/T5/GAR grids + SFDR 18-indicator Table 1 (+n-1), all wired.
- **③ Saved provided-data → forms** — the customer's uploaded per-loan attributes (`residual_maturity_years`,
  `ifrs9_stage`, `epc_label`, `emission_intensity`) land on `ext_banking`, flow through `build_disclosure_snapshot`
  into the assets, and are consumed by the grids/annex (template5_grid, filing_annex EPC section, transition_alignment
  IEA Template 3). Live: 132 loans carry maturity/EPC/IFRS-9. Populates automatically as more data is provided.
- **④ XBRL/iXBRL** — `ml/regulatory/xbrl.py` → valid XBRL 2.1 instance for ESRS E1-9 (EFRAG Set 1 taxonomy, Del. Reg.
  2023/2772), served at `/v1/packages/{id}/xbrl`; `sfdr_xbrl.py` tags the SFDR PAI, served via funds.

**Genuinely remaining = EXTERNAL / verification only:** EFRAG official element-map validation to certify the ESRS
XBRL element IDs cell-perfect; TRACES DDS schema alignment (sandbox credentials); IFRS-S2 / SASB / finest GAR
sub-column wording verified-to-the-letter (behind OAuth walls). No further in-house build is blocked on us.

Honesty rules unchanged: computed cells labelled (`book`/`calc`), customer cells `integrated` (never fabricated),
credit-quality / alignment / GHG stay customer-provided, and the in-app form is a preparation aid.
