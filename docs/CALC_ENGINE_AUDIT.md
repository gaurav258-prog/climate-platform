# Calc-engine audit — static + live-DB verified

**Date:** 2026-07-31 · **Method:** six parallel read-only agents across the pipeline (ingestion, data
quality, processing logic, output verification, consumption, cross-cutting robustness), then every
runtime-verifiable finding confirmed against the live Postgres. **Migration state at audit:** head =
`f1_lane_views_20260731`, single head, nothing pending.

## Verdict

The honesty-first ethos is genuinely enforced at the foundation — append-only `canonical_scores` is a
real DB trigger, "current horizon = zero warming" is airtight, the calibration tier is a *derived* view
(can't be typed), the r²-gate is a non-configurable code constant, and every regulatory assembler
re-respects the publish gate. The discipline stopped short in three places: the **statistical scoring
lane**, the **frozen/canonical record**, and **operational failure modes**. Plus a few concrete bugs.
The DB pass showed most items were *latent or dormant*, not actively wrong — only F2 was live.

## Findings (static + live-DB status)

| # | Finding | DB-verified status | Fixed? |
|---|---|---|---|
| **F2** | Ranged publish gate used **in-sample r²**, not out-of-sample `r2_oos` | ✅ Actively off: 2 crops (Durum-wheat-ES oos .237, Wheat-IR .327) published on optimistic r² | **✅ FIXED** — gate → `r2_oos` (migration `ranged_gate_oos_20260731`), display `fit_r2` → oos, 4 gate sites aligned, test |
| **F1** | 4 physical-risk views missing `score_lane='standing'` filter | ✅ Confirmed on 4 views; **latent** (0 nowcast rows live now; lane exercised = 9,066 retired) | **✅ FIXED** — filter added to all 4 (migration `f1_lane_views_20260731`), invariant test over all such views |
| **Fab** | `flood_sources.py` fabricates gauge/precip via `np.random` | ✅ Dormant — `flood_observations` table never created, no importers | **✅ FIXED** — module deleted + guard test forbids `np.random` in ingestion |
| **Reg** | Feed registry + slide over-claimed sources | ✅ Confirmed (flood=ERA5-runoff not GloFAS; reference=NACE estimates not Climate TRACE/GEM; seismic=EMSC-EU+ESHM20 not USGS/GEM; Sentinel imagery stub) | **✅ FIXED** — registry relabelled honestly with a `maturity` field (live/proxy/partial/on_demand/estimated/planned), surfaced in the Control Center; slide corrected |
| App | Append-only trigger | ✅ Live (`prevent_delete/update_canonical_scores`) — **strength** | — (test added under F1 area TBD) |
| **T1** | Frozen snapshot not reproducible / no `payload_sha256` / no WORM | code-level | ⏳ tier-2 |
| **T2** | Monte-Carlo VaR seeds off unsalted `hash()` → changes on restart | code-level; **dormant** (only assetmgmt VaR path) | ⏳ tier-2 |
| **T3** | E1 own-operations baseline/current but *labelled* with requested scenario/horizon | code-level | ⏳ tier-2 |
| **T4** | Fail-safe signals computed-but-not-wired: **staleness**, geocode **low_confidence**, **missing-input**, **fallback proxy** all reach the dashboard, not the score | code-level; fallback dormant (0 rows) | ⏳ tier-2 |
| **T5** | Confidence Grade never enters the frozen snapshot payload | code-level | ⏳ tier-2 |
| **T6** | `calc_settings`/`reporting_settings` changes: no 4-eyes; calc_settings unaudited | code-level | ⏳ tier-2 |
| **T7** | iXBRL/XBRL regenerated live, never snapshotted (can drift from frozen pack) | code-level | ⏳ tier-2 |
| **T8** | Same asset scoped differently in E1 vs Taxonomy (worst-hazard filter divergence) | code-level | ⏳ tier-3 |
| **T9** | FX treats NULL/blank currency as EUR (docstring says it never does) | code-level | ⏳ tier-3 |
| **T10** | r²=0.40 floor triplicated as literals (no parity test) | partially addressed (all now on `r2_oos`, 0.40) | ⏳ tier-3 (single constant + test) |
| **T11** | No independent challenger for the supply euro; evidence concentration (Cocoa = 1 event; Coffee-BR drought `passed=false` live) | ✅ confirmed | ⏳ tier-3 / disclosure |
| **T12** | No drift / re-validation trigger (validation is one-time) | code-level | ⏳ tier-3 |
| **T13** | Geophysical: ESHM20 fallback rows labelled `eshm20_pga`; EMSC EU-only; USGS/GEM not wired | ✅ confirmed | ⏳ tier-3 (tag fallback distinctly; wire global) |

## The 7 cross-cutting pillars (what an auditor probes beyond the linear pipeline)

Lineage · uncertainty propagation · reproducibility · **fail-safe** · drift monitoring · independent
challenger · invariant tests. The audit found concrete gaps in each; F1/F2/Fab/Reg + the tier-2 batch
close them progressively.

## What shipped this pass (2026-07-31)

- **F2** out-of-sample gate (retires Durum-wheat-ES + Wheat-IR honestly) + regression test.
- **F1** score-lane filter on the 4 unfiltered views + an invariant test over *all* physical-risk views.
- Deleted the `np.random` flood fabricator + a guard test forbidding random generators in ingestion.
- Relabelled the golden-source registry + the investor slide to what actually lands (`maturity` field).

Remaining T1–T13 are tracked as tier-2/tier-3 tasks.
