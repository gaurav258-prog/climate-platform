# Agriculture — operational readiness runbook

**Audience:** whoever takes a design-partner from "the demo works" to "our real CSRD/EUDR filing went out
on our numbers." **Question it answers:** what stands between *built* and *in production for a paying
customer's real, assured filing* — and who does each piece.

Everything in [AGRI_REGULATORY_SCOPE.md](AGRI_REGULATORY_SCOPE.md) is about *which* regulation is ours.
This is about the **non-code operational gaps** on the ones we own. Each item is one of:

- **READY** — works in production as-is.
- **GAP (us)** — code/integration work still on our side.
- **GAP (customer)** — a registration, credential or sign-off only the customer can do.

Honesty rule carries through: we never let a demo convenience read as production-ready. Where a step is
still manual or provisional, the product says so on the page, and so does this doc.

---

## 1. EUDR → TRACES submission

| | |
|---|---|
| **Status** | Tier 1 **READY**; Tier 2 **GAP (us + customer)** |
| **Built** | `assemble_dds()` produces a per-consignment Due Diligence Statement from the plot polygons + satellite forest-loss determinations, with blocker/readiness reasons. The operator files the exported statement in the EU Information System / TRACES and enters the reference number back — nothing is ever quietly auto-filed. |
| **Gap** | Tier 2 is direct submission over the **TRACES API** (no manual re-keying). Two prerequisites: **(customer)** register as an EUDR operator/trader in the EU Information System and obtain API credentials; **(us)** build the TRACES API client + map our DDS fields to their submission schema, and store the returned reference number + status against the consignment. |
| **Owner action** | Customer completes operator registration and shares API access. Then we wire and certify the Tier-2 submit path against the TRACES sandbox before touching production. |
| **Do NOT** | Auto-submit before the customer has reviewed. EUDR liability sits with the operator; the human sign-off stays. |

## 2. XBRL / EFRAG taxonomy binding

| | |
|---|---|
| **Status** | Tagged-data layer **READY**; validated ESEF filing **GAP (us)** |
| **Built** | `build_xbrl_instance()` emits a well-formed XBRL instance — real `xbrli` contexts, units and fact structure, every figure tagged to its ESRS disclosure requirement (E1-9, E3-4/5, E4-5). Concepts sit under a clearly **provisional `tesrs:` namespace**, disclosed on the page and in the file header as "NOT a validated ESEF/iXBRL filing." |
| **Gap** | Production binds those concepts to the **adopted EFRAG ESRS Set 1 XBRL taxonomy** (the official `.xsd`/linkbases), and — for the annual report — produces **iXBRL/ESEF** (inline XBRL embedded in the human-readable report), not standalone XBRL. |
| **Owner action** | **(us)** Obtain the adopted EFRAG taxonomy package once published/final, re-point each concept from `tesrs:` to the official namespace, and validate the instance with **Arelle** (or the customer's filing tool) until it passes. Track the Omnibus timeline — the taxonomy and the mandated concepts are still moving, which is exactly why the reporting basis (scenario, horizon, materiality, period) is a configurable per-org setting rather than a hardcoded constant. |
| **Note** | We deliberately ship the tagged-data layer now so the customer's filing tool has clean, DR-referenced facts to bind. We do not claim it is a filed ESEF document. |

## 3. Geocoder productionization

| | |
|---|---|
| **Status** | **GAP (us)** — fine for demo/onboarding, not for consumer-scale production |
| **Built** | Address → coordinate resolution via **Nominatim** (OpenStreetMap), with a shared thread-safe rate limiter so parallel loaders respect one rate budget, and a street→city→country fallback ladder. |
| **Gap** | The **public** Nominatim instance rate-limits hard, offers no SLA, and carries ODbL attribution/usage terms not meant for production volume. Bulk supplier-list uploads will throttle. |
| **Owner action** | **(us)** Move to either a **self-hosted Nominatim** (own the SLA + rate budget) or a commercial geocoder (Google / HERE / Mapbox) with a caching layer keyed on the normalized address, plus an **address-precision QA** step that flags low-confidence hits for human confirmation rather than silently scoring a bad point. The selectable-autocomplete UI already gives us the confirmation surface. |
| **Positioning** | The *hazard* data stays direct from Europe's & America's satellites & agencies (Copernicus/ECMWF, NASA/USGS). Geocoding is a separate, swappable utility; upgrading it does not touch the golden source. |

## 4. Assurance evidence pack

| | |
|---|---|
| **Status** | Primitives **READY**; packaged auditor bundle **GAP (us)** |
| **Why** | CSRD requires **limited assurance** now (moving toward reasonable). The assurer will ask *how* each number was produced and *who could change it*. |
| **Built** | We already hold every primitive an auditor asks for: the **model-validation / backtest record** (per crop × origin, with r² and the retired-price-claim honesty note), the **`access_audit_log`** (who did what, when), **4-eyes approvals** on material edits and deletes, **provenance** on every reference table, the **honesty gate** (€ withheld where the hazard→yield chain doesn't clear r²≥0.40), and now **immutable report snapshots** — the exact bytes as filed, on a frozen basis. |
| **Gap** | These are not yet exported as a single **auditor-ready evidence bundle**: methodology write-up + data-lineage export + validation record + control evidence (approvals, audit trail) + the specific snapshot under assurance, zipped and cross-referenced. |
| **Owner action** | **(us)** Build an "assurance pack" export keyed on a report snapshot that pulls those primitives into one indexed bundle. Most of the work is assembly, not new data — the spine already exists. |

## 5. Golden-source refresh cadence

| | |
|---|---|
| **Status** | **GAP (us + customer)** — needs an agreed, owned schedule per feed |
| **Why** | A filing is only as current as the feeds under it. Each source refreshes on its own clock; a re-score and (if a snapshot's basis is affected) a re-freeze must follow, with a change log. |
| **Sources & indicative cadence** | Hazard/climate — **Copernicus/ECMWF, NASA/USGS** (rolling; re-score on the reporting cadence, plus event-driven for the early-warning nowcast). Deforestation — **Hansen Global Forest Change** (annual release; re-run EUDR determinations on release). Reference — **GLEIF** (LEI, daily-ish), **Climate TRACE** / **GEM** (periodic). Backtests — refit when a new validated shock year lands. |
| **Owner action** | **(us)** Define, per feed: refresh trigger, the re-score job it kicks, and whether it invalidates a live (un-frozen) basis. **(customer)** Agree the reporting cadence and who signs off a re-freeze. Frozen snapshots never move — a refresh produces a *new* version, preserving the audit line. |
| **Standing** | The score lane invariant holds through refreshes: a live nowcast never retires a calibrated standing climatology, and `canonical_scores` stays append-only. |

---

## One-screen status

| Gap | Status | Blocking who |
|---|---|---|
| EUDR Tier-1 DDS (manual reference-number entry) | READY | — |
| EUDR Tier-2 direct TRACES submit | GAP | customer registration → us |
| XBRL tagged-data layer (provisional namespace) | READY | — |
| XBRL bound to adopted EFRAG taxonomy + iXBRL/ESEF | GAP | us (on taxonomy finalization) |
| Geocoder (demo/onboarding scale) | READY | — |
| Geocoder (consumer-scale, SLA, QA) | GAP | us |
| Assurance primitives (validation, audit, 4-eyes, provenance, snapshots) | READY | — |
| Assurance evidence-pack export | GAP | us |
| Golden-source refresh cadence | GAP | us + customer sign-off |

**Reading this to a design partner:** everything that produces a *number* is production-grade and honest
about its own limits. The gaps are the **last-mile plumbing to a regulator's inbox** (TRACES API, the
official XBRL taxonomy) and the **operational disciplines around a real filing** (production geocoding SLA,
an auditor bundle, a refresh schedule) — each with a clear owner, none of them a rebuild.
