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

## 1. Bank — EBA Pillar 3 ESG risks · `bank_p3esg`  ⚠ largest build gap, mostly computable
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

**We render today** (`_p3esg_annex`): three flat 2-column sections — "Template 5" = value-at-risk (High+) + per-hazard
exposed value (NOT the a–o grid); "GAR (Templates 7–8)" = eligible/not-eligible/not-assessed %; "Transition —
financed emissions" = Scope 3 + total. `p3_transition` (Templates 1–4) is catalogued `none/none`.

**Gap & build.** Rebuild **Template 5** to the official grid — **rows = NACE sector**, **cols = gross carrying
amount + maturity buckets + chronic (h)/acute (i)/both (j)**, *of which physical-risk-sensitive* = our High+
engine; credit-quality cols (k–o) = **customer IFRS-9** (blank/integrated). Build **Template 1** similarly
(NACE rows; gross carrying amount + maturity + PCAF S1/S2/S3 columns; credit-quality = customer). GAR: add
counterparty-type rows + CCM/CCA + eligibility (computed) with **alignment = customer** (so T8 GAR% needs it).
**Computable now:** T5 rows/maturity/chronic-acute/gross-amount; T1 rows/maturity/emissions. **Customer:**
Stage2/NPE/impairment, alignment flags, % company-reported, EPC (Template 2).
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

**We render today** (`_located_annex`): one flat table — eligible / not-eligible / not-assessed / total covered,
% of covered. No objective axis, no stock/flow, no SC/DNSH, no Turnover-vs-CapEx, none of the 8 templates.

**Gap & build.** Build the GAR as **T3 stock by environmental objective** with Turnover/CapEx KPI columns:
eligibility (computed) + alignment (customer) + of-which enabling/transitional (customer). Add the **Art. 7
exclusion** (drop sovereign/central-bank exposures from the denominator) — computable if the book flags them.
Full 8-template set is large; prioritise T0 Summary + T3 stock.
_Source: [CELEX:32021R2178](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178); [Annex VI PDF](https://ec.europa.eu/finance/docs/level-2-measures/taxonomy-regulation-delegated-act-2021-4987-annex-6_en.pdf)._

## 3. REIT — EU Taxonomy Art. 8 (non-financial) + TCFD · `reit_tcfd`  ❗ correctness bug
**Governing text.** A REIT is a **non-financial undertaking** → Del. Reg. 2021/2178 **Annexes I & II**: three KPI
templates — **Turnover / CapEx / OpEx**. Rows: **A. eligible → A.1 aligned (of-which enabling/transitional) ·
A.2 eligible-not-aligned · B. non-eligible · Total**. Columns: activity+NACE, absolute €, proportion %, **SC (6
objectives) · DNSH (6 objectives) · minimum safeguards (Y/N) · enabling/transitional markers · year N & N-1**.
**Full KPIs from 1 Jan 2023.**
**Bug.** `build_annex` routes `reit_tcfd` through `_located_annex`, which renders a **Green Asset Ratio** table —
**GAR is credit-institutions-only.** A REIT must never file a GAR. **Fix:** route REIT to a non-financial
Turnover/CapEx/OpEx template (eligibility computed, alignment customer), not the GAR.

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

## 6. Insurer — climate / NatCat · `insurer_climate`  ❗ builder mismatch
**Governing text.** **No fixed EU quantitative NatCat disclosure template.** Layer 1 = **IFRS S2** (Governance /
Strategy / Risk mgmt / Metrics & targets) with **insurance industry metrics (SASB FN-IN-450a)**: **450a.1 PML from
weather-related natural catastrophes**; **450a.2 cat monetary losses by event type & geographic segment, net &
gross of reinsurance**; **450a.3 underwriting/risk-integration narrative**. Layer 2 = **Solvency II ORSA**
(principles-based scenario narrative) + the **SCR NatCat sub-module** (a capital grid, not a disclosure template).
*(Exact FN-IN-450a code wording behind an IFRS OAuth wall → unverified-to-the-letter.)*
**We render today.** `insurer_climate` routes through **`_located_annex`** — the **bank TCFD builder** — so it shows
GAR / PCAF / value-at-risk-by-hazard, and the catalog's `natcat_eal` / `sum_insured_at_risk` may **not surface**
(the builder keys off `hazard.*`/`taxonomy.*`).
**Gap & build.** Give the insurer its **own annex**: **PML by peril & geography** (we compute sum-insured-at-risk +
EAL), **cat loss by event type / geography**, and an **underwriting-integration** narrative — mapped to the IFRS S2
metric headings. Stop reusing the bank GAR/PCAF layout.

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
1. **Fix correctness bugs first:** REIT → non-financial Turnover/CapEx/OpEx template (not GAR); insurer → own
   IFRS-S2 annex (not the bank builder).
2. **Pillar 3 Template 5** — real NACE × maturity × chronic/acute/both grid (gross carrying amount basis);
   credit-quality columns = customer. *Mostly computable now — top build.*
3. **Pillar 3 Template 1** — NACE × maturity × PCAF-emissions grid.
4. **Taxonomy GAR** — T0 Summary + T3 stock by objective (eligibility computed, alignment customer); Art. 7 exclusion.
5. **SFDR** — exact Table 1 (6 cols, 18 rows, verbatim wording) + year n-1 + narrative persistence + Tables 2–3 menu.
6. **ESRS** — label E3-4 as stress-proxy vs metered m³; EFRAG element map is the external ESEF blocker.
7. **EUDR** — add the two missing Annex II fields; TRACES schema alignment (external).

Honesty rules unchanged: computed cells labelled (`book`/`calc`), customer cells `integrated` (never fabricated),
credit-quality / alignment / GHG stay customer-provided, and the in-app form is a preparation aid.
