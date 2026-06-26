# Climate Intelligence Platform — Investor Brief
*Draft v0.1 · June 2026 · Confidential*

---

## The Thesis

Physical climate risk is the largest unpriced externality in European financial markets. The data to measure it — satellite imagery, reanalysis weather, river discharge — has existed for years as EU open data. What has not existed is a platform that fuses it at cell-level precision, turns it into a legally defensible score, and delivers it simultaneously to the three buyers who need it most: parametric insurers, regulatory compliance teams, and government emergency managers.

We built that platform.

---

## The Problem

**Basis risk kills parametric insurance.** A parametric policy pays when an index crosses a threshold — not when a loss actually occurs. If the index is too coarse (5–25km grid cells, the industry norm), a client's warehouse floods while the nearest index point stays dry. The payout never fires. The client doesn't renew. This is the primary reason parametric penetration in Europe remains below 3% of total insurance premium despite a decade of commercial interest.

**CSRD creates a compliance obligation with no data infrastructure.** The EU Corporate Sustainability Reporting Directive requires ~10,000 European companies (1,000+ employees, revised scope) to disclose quantified physical climate risks against their asset portfolios. Most of them have no idea where to get sub-kilometre flood, heat, and wildfire scores for their European locations. The first CSRD reporting wave is live. The second wave is filing now.

**Emergency management runs on gut and phone calls.** During the 2021 Ahr Valley flood — 134 dead, €33B in losses — coordination between civil protection agencies relied on generic weather alerts, not cell-level risk scores. Response was reactive. Rescuers pre-positioned in the wrong districts. The data existed in ERA5 and GloFAS. It was never assembled into an actionable operations view.

These are three distinct buyers with three distinct procurement paths. The underlying data requirement is identical.

---

## The Platform

**What it does.** The platform ingests five open satellite and reanalysis data sources daily — Copernicus Sentinel-1 SAR (radar backscatter), Sentinel-3 (land surface temperature), ERA5-Land (meteorological reanalysis), GloFAS (river discharge), and NASA FIRMS (active fire radiative power) — and fuses them into a single canonical risk score per H3 cell per hazard per day.

**How it scores.** XGBoost models trained on historical event data (2021 Ahr flood, 2022 Gironde wildfire, 2003 European heat event) output a 0–100 risk score with confidence interval, 24h velocity, and SHAP factor decomposition. Scores are append-only — no record is ever updated or deleted. Every score carries a model version, data vintage, and audit reference.

**What it delivers.**

| View | Audience | Core action |
|------|----------|-------------|
| Risk Map | All | H3 hexagon map, 11-day time scrubber, alert feed |
| Operations | Civil protection, emergency mgmt | Region risk table, action dispatch board |
| Parametric | Reinsurers, ILS funds | Trigger state per policy, threshold bars, event log |
| Compliance | Banks, corporates | Portfolio exposure, CSRD/ECB/EIOPA packages, XBRL export |

**Data cost.** Zero. Every data source is EU open data (Copernicus) or openly licensed reanalysis (ERA5, GloFAS, FIRMS). There is no data acquisition line in our cost structure. This is structural, not a startup subsidy.

---

## Technical Differentiation

**1. Resolution — the basis risk fix.**
We score at H3 resolution 8: cells of ~0.74km². Descartes Underwriting, RMS, and most catastrophe models work at 5–25km grid resolution. At 25km, a single cell covers 625km² — enough to contain an entire flood event and its dry surroundings simultaneously. At 0.74km², the cell is the street block. Lower basis risk is not a feature. It is the prerequisite for parametric products that actually work, and it is the reason clients renew.

**2. Cost structure — open data moat.**
Competitors pay for proprietary satellite data: Planet Labs, Maxar, commercial SAR providers. These are real costs — $0.5–5 per km² per acquisition, running to millions per year at scale. We use Sentinel-1 (free, 6-day repeat, 10m resolution) and ERA5 (free, hourly, 31km reanalysis). The margin advantage compounds as we scale. It also means we can price below incumbents while maintaining better unit economics.

**3. Dual-use platform — the lane no one occupies.**
The canonical risk score that fires a parametric trigger in our Parametric view is the same score that populates a CSRD disclosure package in our Compliance view. No competitor spans both. Descartes Underwriting does not produce regulatory packages. Jupiter Intelligence does not design parametric triggers. We do both from one score, one model version, one audit trail. This matters commercially: a bank that buys our compliance product is already holding the data that could underwrite a parametric policy on its own property portfolio. The cross-sell is a single button.

---

## Market Sizing

*Backward-deduction methodology — all assumptions stated explicitly.*

**Parametric insurance — Europe.**
European parametric premium: $3.82B in 2025, growing at ~10% CAGR to $8.99B by 2034 (GMI, FundamentalBI). Data and technology spend in parametric insurance runs at 2–3% of gross written premium — the index license, trigger engine, and settlement infrastructure. At 2.5% take rate: **€95M addressable today, €225M by 2034.** Our trigger design fee (one-time, per product) is additive to this and not captured in traditional market sizing.

**Physical climate risk analytics — Europe.**
Global climate risk analytics: $1.8B in 2025, growing at 19% CAGR to $7.7B by 2034 (Fortune Business Insights). European share: ~35% = **$630M (2025) → $2.7B (2034).** Our addressable slice — physical risk data for regulatory and operational use, excluding transition risk and ESG ratings — is approximately 40% of the European total: **€250M today, €1B+ by 2030.**

**CSRD compliance — physical risk data component.**
Revised CSRD scope: ~10,000 European companies with 1,000+ employees. ESRS E1 requires quantified physical risk disclosure per asset location. Average physical risk data spend per company: €30–100K per year (benchmarked against Jupiter Intelligence enterprise pricing and Moody's RMS subscription tiers). **SAM: €300–500M per year, recurring.** Phase 1 companies (largest 1,000) are already filing. Phase 2 is live from 2026.

**Combined European SAM: €700M–900M by 2028.**
Our Y3 target of €7.5M ARR represents ~1% of SAM — a conservative entry position given two years of commercial operation by that point.

---

## GTM and Revenue Model

**Sequencing.** We enter through parametric insurance first. It has the shortest sales cycle (3–6 months), the clearest ROI (a trigger either fires correctly or it doesn't), and no procurement committee. One reinsurance cat desk is enough to validate the model. We run regulatory compliance in parallel from day one — it's a 12–18 month sale, but CSRD deadlines are forcing decisions now. Government and agriculture follow in Years 2–3.

**Three revenue levers.**

*Parametric (highest LTV, highest moat):*
- **Trigger design fee** — one-time, €50–200K. We work with the client to define the index, validate basis risk against their actual loss data, and structure binary or step-scaled payout schedules. This is not consulting — it is the product. A client who has spent €100K on trigger design does not walk away from the €80–150K annual license.
- **Annual index license** — €80–300K/yr. Real-time score feed for each parametric product.
- **Settlement event fee** — €5–25K per confirmed trigger event. Usage-based, aligned with client value.
- *Average parametric client LTV (design + 3yr license + events): €500K–1.2M.*

*Regulatory (highest volume, most recurring):*
- **Platform subscription** — €60–400K/yr, based on location count and framework count (CSRD, ECB, EIOPA, MAS E-12).
- **Regulatory package** — €5–15K per generated package. XBRL export, audit trail, maker/checker sign-off.
- **API access** — €20–80K/yr for clients embedding scores in their own risk models.

*Government / emergency management:*
- **Early warning subscription** — €40–200K/yr. Multi-hazard dashboard, SMS/webhook alert API.
- **Operations API** — €30–150K/yr. Action board integration with civil protection dispatch systems.

**Three-year projection.**

| Year | Clients | Parametric | Regulatory | Govt/Other | ARR |
|------|---------|------------|------------|------------|-----|
| 2025 | 4–5 | €300K | €120K | — | **€420K** |
| 2026 | 15–20 | €1.5M | €900K | €200K | **€2.6M** |
| 2027 | 40–55 | €4.0M | €2.6M | €900K | **€7.5M** |

---

## Competitive Positioning

**The closest direct competitor is Descartes Underwriting.** Founded Paris 2019, raised $141M total (Series B 2022, Series C June 2025), valued above $500M. Clients include Munich Re and AXA XL. They use ML and satellite data to design and underwrite parametric triggers. This is real competition and investors should expect it to be named in due diligence.

**Where we differ from Descartes — specifically:**

| Dimension | Descartes Underwriting | This platform |
|-----------|----------------------|---------------|
| Cell resolution | ~5–10km grid | 0.74km² (H3 r8) |
| Data acquisition cost | Proprietary satellite (real OpEx) | Zero (Copernicus + ERA5 open data) |
| Regulatory compliance | Not offered | CSRD / ECB / EIOPA packages built-in |
| Business model | Carrier / MGA (takes risk on book) | Pure data & platform (no underwriting risk) |
| Geography focus | Global, US-weighted | Europe-first, EU data-native |

**On resolution:** this is the critical difference for parametric trigger design. At 0.74km², basis risk falls to near zero for most European flood and wildfire events. At 5–10km, basis risk remains the primary objection to parametric adoption. We are not claiming superiority — we are claiming a structurally different product.

**On business model:** Descartes operates as an MGA — it takes underwriting risk on the policies it writes. We do not. We sell data. This means we have no accumulation exposure, no reinsurance cost, and no regulatory capital requirement as an insurer. Our gross margins are data-platform margins (70–80%), not insurance margins (10–25%).

**Other players and why they are not direct competition:**
- *Jupiter Intelligence* — physical risk scoring for bank stress testing, no parametric capability, US-centric
- *Moody's RMS / Four Twenty Seven* — coarse-grid cat models, priced for incumbents (€500K+ enterprise), not structured for dual-use
- *MSCI Climate / S&P Sustainable1* — ESG-bundle products, physical risk is one field in a broader dataset, not a standalone scored product
- *Arbol / Kettle* — US-focused, single-hazard, no regulatory angle

**The un-occupied lane:** parametric trigger design + regulatory compliance packages on one hyper-local score engine, built on EU open data, for the European market. No current player occupies this position.

---

## EU Grant & Impact Narrative

*This section is written for EU grant audiences (Horizon Europe, EIC Accelerator, LIFE programme). The commercial narrative above remains primary for VC and strategic investors.*

**EU programme alignment.**
The platform is built entirely on data from the EU Copernicus Earth Observation programme — the EU's own satellite infrastructure. Every score produced is traceable to EU public data. This is EU data sovereignty in practice: no dependency on US or commercial satellite operators, no proprietary data black boxes.

**EIC Accelerator 2026 alignment.**
The EIC Accelerator's "Deep Tech for Climate Adaptation" challenge (2026 budget: €634M across all challenges) is a direct fit. Our platform addresses the challenge brief — technology that reduces the impact of climate-related hazards through early warning, risk quantification, and adaptive response infrastructure.

**Horizon Europe 2026–2027 alignment.**
The European Commission has dedicated €4.9B to climate action in the Horizon Europe 2026–2027 work programme. The EU Mission on Adaptation (€226M) funds exactly what this platform operationalises: accelerating climate adaptation action and supporting concrete adaptation solutions on the ground.

**Impact framing — what the platform enables.**

*Lives and assets protected.* By providing cell-level risk scores 24–72 hours before a flood or wildfire peak, government emergency managers can pre-position rescue teams, open shelters, and issue targeted evacuation orders — rather than reacting after the event. The 2021 Ahr Valley flood killed 134 people and caused €33B in damage. Our Operations view is designed for exactly this scenario: the right action, dispatched to the right district, before the peak.

*Insurance coverage where it was not viable.* Parametric basis risk has historically made flood and drought insurance uneconomic in rural and peri-urban areas. At 0.74km² resolution, coverage can be extended to smallholder farms, municipal infrastructure, and SME supply chains that traditional insurance cannot price. This directly supports the EU's stated goal of closing the insurance protection gap.

*Regulatory compliance at scale.* CSRD physical risk disclosure is mandatory but technically demanding. Providing a shared data infrastructure — EU-origin scores, auditable, XBRL-exportable — allows 10,000 European companies to comply without each building their own climate modelling capability. This reduces the administrative burden the Commission estimated at €4.4B/year under the original scope.

**Proposed EU grant structure (three routes):**

| Route | Programme | Fit | Funding range |
|-------|-----------|-----|---------------|
| EIC Accelerator Challenge | Deep Tech for Climate Adaptation | Direct — platform is the deep tech | €500K–2.5M grant + equity |
| Horizon Europe Innovation Action | Climate adaptation operational tools | Strong — cross-border, government users | €2–5M consortium |
| LIFE Climate Action | Flood/wildfire risk reduction | Good — demo sites in 2+ member states | €1–3M co-fund |

*Note on impact metrics: specific claims (lives protected, € losses avoided) should not be asserted until pilot data from operational deployments is available. Grant committees treat unsupported impact numbers as a credibility risk. The framing above is deliberately mechanistic — what the platform enables — rather than predictive.*

---

## The Ask

*[SEED ROUND TBD]*

Use of proceeds:
- Model validation and EU-wide coverage expansion (flood: Rhine, Danube, Po; wildfire: Mediterranean arc; heat: urban centres)
- First three commercial pilots (1–2 parametric, 1 regulatory)
- Regulatory certification for parametric index use (Lloyd's, BaFin, AMF)
- EIC Accelerator application Q3 2026

---

*Sources: GMI Insights parametric insurance market report; Fortune Business Insights climate risk analytics report; FundamentalBI European parametric market; Descartes Underwriting Series C announcement June 2025; EU Commission Horizon Europe 2026–2027 work programme; EIC Accelerator 2026 work programme; ESRS E1 physical risk disclosure requirements.*
