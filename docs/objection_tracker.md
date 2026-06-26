# Objection Tracker — Climate Intelligence Platform
*Living document. Update after every investor meeting, customer conversation, or pilot engagement.*

**How to use:** After each conversation, log the exact words used, the context (who said it, when), and whether the current answer landed. If the answer didn't land, note what they pushed back on and draft a revised response. The goal is to reach a version of each answer that closes the conversation — not extends it.

---

## Format

Each objection entry has:
- **Verbatim (or close)** — the exact phrasing, because wording matters
- **Who raises it** — investor type, buyer type, stage of conversation
- **Current best answer** — the v-current response
- **What to watch for** — signals the answer is landing vs. not landing
- **Conversation log** — date, who, what happened, what to change

---

## OBJ-01 · The Free Data Objection
**"Copernicus is free. Can't anyone just build this in six months?"**

**Who raises it:** Seed VCs in technical due diligence · Any engineer-founder investor · Occasionally reinsurance quants

**Current best answer (v1 · June 2026):**

Yes — the data is free. What is not free:
1. The SAR processing pipeline (14 months to build; orbit correction, thermal noise removal, radiometric calibration, terrain correction, speckle filtering — each domain-specific with non-obvious failure modes)
2. Multi-source fusion at three spatial resolutions (10m Sentinel → 0.74km² H3 cell) — significant engineering, not a library call
3. XGBoost models calibrated against specific historical European events with ground-truth inundation maps — a new entrant cannot replicate this history without the same events
4. Parametric trigger design methodology — the index construction expertise that a reinsurer's cat desk will accept
5. Lloyd's / BaFin / AMF certification: 18–24 month process, filed once, creates a time-gated moat

The framing that lands: **"Free inputs are our cost structure advantage, not a vulnerability."** Any competitor using commercial satellite data carries an OpEx line we don't. We can price 30% below them and still run 70–80% gross margins.

Bloomberg analogy: Bloomberg doesn't own Fed policy announcements. They charge for the terminal. We don't own Copernicus. We charge for the certified trigger index built on it.

**What to watch for:**
- ✓ Answer is landing: investor moves to "ok so what's the certification timeline" — they accepted the moat, now want to size it
- ✗ Answer is not landing: investor says "but Google / a well-funded team could just do this" — they're not convinced by the engineering depth argument, pivot to the certification moat instead

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## OBJ-02 · The Descartes Objection
**"Descartes raised $141M and has Munich Re. Why not just partner with them?"**

**Who raises it:** Strategic investors · Reinsurance capacity providers · Any investor who googled the space

**Current best answer (v1 · June 2026):**

Different business models, different buyers. Descartes is an MGA — they take underwriting risk on the book. We are a data platform — zero underwriting risk, no capital requirement, 70%+ gross margins vs. their MGA economics (10–25%). They sell to the cedant side (corporates buying coverage). We sell to the capacity side (cat desks designing products) and the compliance side (CFOs filing CSRD).

Three specific gaps Descartes doesn't fill:
1. Resolution: ~5–10km vs. our 0.74km² — the critical difference for basis risk
2. Regulatory compliance: no CSRD / ECB / EIOPA packages
3. Government operations: no emergency management view

Their $141M valuation confirms the category is real. Our addressable surface is wider, at finer resolution, with better unit economics.

**What to watch for:**
- ✓ Landing: "So you're more like the infrastructure layer and they're the insurer" — good reframe, accept it
- ✗ Not landing: "But they could just add a regulatory module" — counter: they'd have to rebuild on a different data model; their product is built around underwriting risk, not score transparency; and they'd still be at 5–10km resolution

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## OBJ-03 · The Statistical Robustness Objection
**"Three training events isn't statistically robust."**

**Who raises it:** Reinsurance actuaries · Technical investors · Academic reviewers (for grant applications)

**Current best answer (v1 · June 2026):**

Two parts:

1. **Architecture answer:** The model isn't pre-calibrated for every client. The trigger design phase validates basis risk against the specific client's actual loss history for their specific geography. Generic model + client-specific calibration is the correct architecture for parametric — not a single global model claiming to predict everywhere.

2. **ERA5 answer:** ERA5 provides 40 years of hourly reanalysis data (1984–present). Every prospective client's historical exposure can be back-tested against our index before the first live policy is written. A client with 10 years of claims history can validate the index against all 10 years. This is more back-test depth than most CAT models offer.

**What to watch for:**
- ✓ Landing: "OK so the client validation is the robustness mechanism" — correct, confirm
- ✗ Not landing: "But the model itself is trained on three events" — this is technically true; the counter is that we're not selling a global climate model, we're selling a local trigger index, and local trigger indices are always validated client-by-client

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## OBJ-04 · The CSRD Commoditisation Objection
**"CSRD compliance tooling is becoming a commodity. Why won't this be free in two years?"**

**Who raises it:** Enterprise SaaS investors · Banks already evaluating multiple CSRD tools

**Current best answer (v1 · June 2026):**

Generic CSRD disclosure tooling (carbon calculators, ESG wrappers) is commoditising. Physical risk scoring at 0.74km² cell level requires satellite data fusion that no SaaS company is going to give away — the engineering cost to build it is the moat, not a licensing fee that disappears.

More important: our CSRD product shares the score engine with our parametric product. A bank that buys compliance is already holding the infrastructure for parametric coverage on their corporate clients. That cross-sell doesn't exist in any pure-play CSRD tool. The CSRD product is both a standalone revenue line and a distribution channel into a different buyer (the cat desk vs. the CFO office).

**What to watch for:**
- ✓ Landing: "So the CSRD product is the top of the funnel for parametric" — good framing, accept it
- ✗ Not landing: "But MSCI and Moody's already have this" — they have coarse-grid (~25km) physical risk flags as one field in a broad dataset. At 0.74km², per-cell, per-hazard, per-day with a SHAP decomposition and XBRL export — no, they don't have this

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## OBJ-05 · The Trust/Incumbents Objection
**"Why would a reinsurer trust a startup index over RMS or AIR?"**

**Who raises it:** Lloyd's syndicates · Cat desks · Risk managers who have existing RMS/AIR contracts

**Current best answer (v1 · June 2026):**

RMS and AIR produce cat models for retrospective loss estimation and capital allocation. They do not produce daily parametric trigger indices. No current RMS or AIR product produces a daily H3-cell score that can serve as a parametric payout trigger. The gap is real, not framing.

Trust is answered by process, not brand:
- Certification (BaFin, Lloyd's, AMF) — the index is third-party validated
- Back-test package — 40 years of ERA5, their actual claims history, SHAP decomposition showing which factors drove each score
- The design fee engagement — a cat desk that has reviewed all of this is not trusting a startup; they are trusting a certified, auditable instrument

Historical point: parametric as a category was built by startups. Arbol, Descartes, Kettle — none started with a 30-year brand. They started with a better index design.

**What to watch for:**
- ✓ Landing: "So the design fee engagement is effectively a validation process" — yes, confirm
- ✗ Not landing: "We only work with established providers" — this is a procurement policy objection, not a product objection; ask what certification they require and work backward to the timeline

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## OBJ-06 · The EU Market Size Objection *(anticipated — not yet raised)*
**"Europe is too small for venture-scale returns. Why not go global from day one?"**

**Who raises it:** US-leaning VCs · Global reinsurers with US-heavy portfolios

**Current best answer (v1 · June 2026):**

Draft only — needs refinement after first time this is raised.

Europe-first is not a market size constraint — it is a regulatory first-mover position. CSRD, ECB climate stress testing, and EIOPA Solvency II physical risk requirements are the strictest climate risk disclosure rules anywhere in the world. The frameworks being built here will be exported — as EU frameworks often are (GDPR → global data law; CSRD → global supply chain due diligence). Being the reference platform when those frameworks land in Asia-Pacific and Latin America is worth more than a global build that tries to do everything from day one with insufficient depth in any market.

Copernicus is also Europe-first. ERA5 global coverage exists but with different data density. The model performance claims we can make for European events (Ahr 2021, Gironde 2022, 2003 heat) are more defensible than claims for markets where we have less ground truth.

**What to watch for:**
- ✓ Landing: "OK so Europe as a regulatory beachhead" — confirm, GDPR analogy tends to land
- ✗ Not landing: Still under-developed — this answer needs sharpening after the first live challenge

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## OBJ-07 · The Copernicus Outage / Data Gap Risk *(anticipated — not yet raised)*
**"What happens if Copernicus has a data gap or Sentinel-1 goes offline?"**

**Who raises it:** Technical due diligence · Risk-focused reinsurance actuaries

**Current best answer (v1 · June 2026):**

Draft only — needs refinement after first time this is raised.

Three mitigations:
1. **Redundancy within the stack:** We use five data sources. If Sentinel-1 SAR is unavailable, ERA5 precipitation + GloFAS river discharge still scores flood risk. If FIRMS is unavailable, Sentinel-3 land surface temperature still scores heat. No single source is a single point of failure.
2. **ERA5 as the backbone:** ERA5 is the European Centre for Medium-Range Weather Forecasts (ECMWF) reanalysis product — the backbone of global weather modelling. It has not had a significant outage. It is not a satellite; it is a computed reanalysis product, which means even historical satellite data gaps are reconstructed.
3. **Contractual coverage clauses:** Parametric trigger contracts can include a "fallback index" clause — if the primary score cannot be computed due to a data gap, the contract falls back to a secondary trigger (e.g., river gauge reading from national services). Standard practice in parametric design.

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

## New Objections — Blank Template

When a new objection is raised that isn't in this tracker, log it here and draft a first response:

### OBJ-XX · [Title]
**Verbatim:** ""

**Who raised it:** [Name / role / organisation if appropriate]  
**Date first raised:**  
**Context:** [What stage of conversation — initial pitch / diligence / pilot negotiation]

**Draft answer (v1):**

**What to refine:**

**Conversation log:**
| Date | Who | Their exact words | How it landed | What to refine |
|------|-----|-------------------|---------------|----------------|
| — | — | — | — | — |

---

*Last updated: June 2026 · Owner: Gaurav*
