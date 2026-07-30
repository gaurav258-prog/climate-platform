# The other side of the value chain — a regulator/supervisor strategy

**Audience:** founder + investor conversations. **Question it answers:** we serve the *reporting entity*
(supply side). Is there a real, ownable business serving the *supervisor* (demand side) built from the
same golden-source engine — and how would we reach it? **Verdict:** yes, and it's high-reuse. The fastest
route to market is a **partner channel (Regnology-type SupTech), not direct public procurement.** This brief
is grounded in current facts (sources at the end); treat named competitors as a first read, not an audit.

---

## 1. The thesis in one paragraph

A supervisor cannot take a reported climate/deforestation number on trust — its whole job is to *verify,
aggregate and act* on what regulated entities file. Verification needs an **independent ground truth**;
aggregation needs a **portfolio/sector engine**; risk-targeting needs a **per-entity risk score**. We
already own all three (the any-address satellite engine, H3 roll-up, per-plot scoring). Pointing them at
*filings* instead of at *our own tenants* turns the reporting product into a **supervisory product** with
very little new build — the genuinely two-sided move.

## 2. The regulator's world — the two arenas we actually touch

### Arena A — EUDR competent authorities (closest to our agri engine)
The EUDR runs on **risk-based enforcement** that is now live and quantified:
- A **country benchmarking** system (low / standard / high risk) went live **22 May 2025** (~140 low,
  ~50 standard, 4 high: Belarus, Myanmar, North Korea, Russia).
- National **competent authorities must physically check** a mandated share of operators by risk tier:
  **1% (low) / 3% (standard) / 9% (high)** of operators *and* of product quantity.
- Authorities must **verify Due Diligence Statements** — confirm from time-stamped satellite analysis that
  land wasn't deforested post-31-Dec-2020. Stronger *independent* verification is required for high-risk.
- The infrastructure is **not ready**: TRACES/the EU Information System wasn't fully operational for the
  Dec-2025 deadline, and the **JRC Observatory** forest layer is not fully operationalized.

**Read:** authorities have a legal duty to independently verify claims, a mandated check volume, and *no
finished tool* to do it at scale. That is a precise, funded, unmet need shaped exactly like our engine.

### Arena B — financial supervisors (ECB / EBA; our bank & insurer verticals)
- The **2025 EU-wide stress test integrated climate physical risk** (EBA + NGFS scenarios); the ECB works
  at **municipality granularity** (≈34% of exposures sit in physically-affected municipalities).
- Climate & nature risk is a standing **ECB/EBA supervisory priority**; a 2026 ECB report sets good
  practices for climate & nature stress testing.

**Read:** supervisors are actively pulling *granular physical-risk* data into prudential supervision — the
same physical-risk layer our finance verticals already produce, but consumed top-down across a system.

### The data sink — ESAP
The **European Single Access Point** opens **10 July 2027**; sustainability/Taxonomy/CSRD data enters in
the **Jan-2028** wave, exposed to regulators and the public via a **public API**. Every CSRD filing lands
in one queryable place — the natural plug-in point for cross-filer verification and aggregation tooling.

## 3. The unmet need → our capability (the module)

| Supervisor need | Evidence it's real | Our engine, pointed the other way | Reuse |
|---|---|---|---|
| Independently verify a filed deforestation/hazard claim | EUDR mandates independent verification; JRC tool not ready | Re-run our determination on the filed geolocations → **diff vs claim** | **have** — any-address engine |
| Hit a mandated check volume with scarce inspectors | 1/3/9% risk-based checks | Rank filers/consignments by **inspection priority** | new: scoring view |
| See systemic exposure across all filers | ECB municipality-level physical-risk aggregation | H3 roll-up → **sector / national hotspot map** | **have** — H3 + roll-up |
| Ingest filings at scale, machine-readable | ESAP public API from 2028; TRACES DDS | We already **emit** XBRL/DDS — flip to **receive** | partial |
| Spot greenwashing / outliers | supervisory priority | Peer-outlier detection on one golden source | new: analytics |
| Govern & audit the oversight itself | any supervisory workflow | RBAC · 4-eyes · immutable snapshots · audit | **have** — governance spine |

The load-bearing asset is **independent verification** — the one thing a supervisor can't outsource to the
supervised. It's also the one thing our satellite engine does natively and most competitors don't.

## 4. Named target buyers (first pass)
- **EUDR competent authorities** in high-import Member States (Germany/BLE, Netherlands/NVWA, France, Belgium) + EU customs.
- **DG-ENV / the JRC Observatory** itself — a verification/benchmark layer where their own tool is late.
- **ECB Single Supervisory Mechanism, EBA, national central banks / NGFS members** — physical-risk data for stress testing & Pillar 3.
- **ESAP / ESMA** — as an analytics layer over the filed corpus (later).

## 5. Go-to-market — partner channel, not direct procurement
Public procurement is slow and relationship-heavy. The leverage move is to be the **physical-climate
ground-truth layer inside an incumbent SupTech stack**:
- **Regnology** is the archetype and the venture's intended distribution layer: **50+ regulators/tax
  authorities, 7,000+ financial institutions**, and a **Supervisory Hub (RSH)** already covering the full
  supervisory lifecycle (collection → validation → analytics → real-time risk signals) with an AI
  orchestration layer ("straight-through supervision"). It has the doors and the collection plumbing; it
  does **not** have an independent satellite climate/deforestation ground truth. That's a clean fit: we
  supply the truth layer, they supply distribution and the workflow shell.
- Same logic for deforestation-specialist channels already selling to authorities (GFW/WRI ecosystem,
  audit-record vendors), where our validated **€-at-risk + calibrated methodology** is the differentiator.

## 6. Independence — the positioning that must be clean
A supervisor won't buy a tool that scores both the supervised and the supervisor from one cosy vendor.
Resolve it explicitly:
- Sell the regulator side as **independent verification against a transparent, published methodology**,
  running on the **regulator's own instance / own golden source** — not "we grade both sides."
- Publish the method and the honesty gate (r² ≥ 0.40; euro withheld where the chain isn't validated). The
  same transparency that wins trust on the entity side is the credibility asset on the supervisor side.

## 7. Competitive landscape (first read — verify before an investor deck)
- **Deforestation monitoring** (SuperVision.earth, TraceX, Koltiva, Meridia, Satelligence, GFW/WRI) — mostly
  serve the *operator* and mostly *flag risk*; few deliver a **competent-authority verification** product,
  and none tie it to calibrated financial effect.
- **SupTech collection** (Regnology, and the broader central-bank RegTech field) — own the pipes and the
  workflow, **not** an independent physical-climate ground truth. → partner, not competitor.
- **Climate-risk data** (Jupiter, XDI, S&P/Moody's) — sell hazard scores to firms and some supervisors, but
  not per-plot verification of filings nor the deforestation truth.
- **Whitespace:** the *competent-authority / supervisor verification-and-aggregation* product built on an
  independent satellite ground truth with a calibrated €-link is essentially unoccupied.

## 8. Build & sequence (high reuse; staged)
1. **Reuse audit** — the platform-operator cross-tenant console is already a supervisor-shaped surface;
   catalogue exactly what transfers (any-address engine, H3 roll-up, snapshots, RBAC/4-eyes/audit).
2. **v0 — independent-diff** — ingest one filed DDS/XBRL, re-run our determination, render *claimed vs our
   truth*. This is the demo that sells the whole idea and is the cheapest thing to build.
3. **v1 — aggregate & risk-target** — cross-filer H3 rollup + an inspection-priority queue mirroring the
   1/3/9% regime.
4. **Channel pilot** — take v0/v1 to Regnology (or a deforestation-authority channel) as the ground-truth
   layer, not a direct-sales motion.

## 9. Honest risks
- **Procurement & political** cycles are long; mitigated by the partner channel, not removed.
- **Independence** must be governance-enforced, not just claimed.
- **Data-authority overlap** — JRC/Copernicus provide *some* of this publicly; our edge is the calibrated
  €-link, per-plot verification workflow, and the honesty gate, not raw imagery.
- **Regulatory timing** (Omnibus, TRACES/ESAP slippage) moves the goalposts — the configurable reporting
  basis already absorbs that on the entity side.

## 10. Recommendation
Build the **v0 independent-diff** prototype from the base engine (cheap, high-signal), position it for a
**Regnology-type channel**, and keep the independence line clean. It's the same golden source earning a
second, structurally-defensible revenue line — and it's the concrete expression of the venture's
"Regnology distribution" layer.

---

### Sources
- EUDR country benchmarking & first risk list (May 2025): https://www.preferredbynature.org/news/european-commission-publishes-first-list-country-benchmarks-under-eu-deforestation-regulation
- EUDR risk-based check volumes (1/3/9%) & enforcement: https://www.coolset.com/academy/eudr-compliance-and-enforcement · https://tracextech.com/country-benchmarking-in-eudr/
- EU Information System / TRACES registration & readiness: https://tracextech.com/eu-information-system/
- Competent-authority verification & JRC Observatory status: https://tracextech.com/competent-authorities-under-the-eudr/ · https://www.globalforestwatch.org/blog/data-and-tools/satellite-data-eu-regulation-deforestation-free-supply-chains/
- Regnology Supervisory Hub / scale (50+ regulators, 7,000+ FIs): https://www.regnology.net/en/solutions/for-regulators/regnology-supervisory-hub/ · https://www.centralbanking.com/awards/7941536/technology-services-regulatory-regnology
- ESAP timeline & ESG phase (opens 10 Jul 2027; sustainability from Jan 2028; public API): https://www.securities-services.societegenerale.com/en/insights/views/news/esap-european-single-access-point-the-platform-will-open-on-july-10-2027/ · https://www.europarl.europa.eu/legislative-train/theme-an-economy-that-works-for-people/file-european-single-access-point
- ECB/EBA 2025 climate physical-risk stress test (municipality granularity): https://www.ecb.europa.eu/press/financial-stability-publications/macroprudential-bulletin/html/ecb.mpbu202511_04.en.html · https://www.esgtoday.com/eba-integrates-climate-risk-into-eu-banking-stress-test/
