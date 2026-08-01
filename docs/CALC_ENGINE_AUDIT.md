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
| **T1** | Frozen snapshot not reproducible / no `payload_sha256` / no WORM | code-level | **✅ FIXED (v1.52)** — `snapshot_worm_20260731`: `payload_sha256` + `engine_versions` (impact/fit/feed/code-SHA/gate) stamped at freeze + back-filled; WORM trigger blocks UPDATE/DELETE; `get_snapshot` re-verifies (`hash_verified`); assurance-pack manifest carries the integrity block. Tests: unit + integration. |
| **T2** | Monte-Carlo VaR seeds off unsalted `hash()` → changes on restart | code-level; **dormant** (only assetmgmt VaR path) | **✅ FIXED (v1.53)** — seed derived from a stable SHA-256 digest (`valuation_discount.py`); cross-process determinism test (`test_var_determinism.py`, runs two interpreters at different PYTHONHASHSEED). |
| **T3** | E1 own-operations baseline/current but *labelled* with requested scenario/horizon | code-level | **✅ FIXED (v1.55)** — `list_sites_with_risk` now basis-scoped; csrd_e1 reads own-ops on the requested scenario/horizon; taxonomy_adaptation declares its present-state basis. Test. |
| **T4** | Fail-safe signals computed-but-not-wired: **staleness**, geocode **low_confidence**, **missing-input**, **fallback proxy** all reach the dashboard, not the score | code-level; DB-verified all LATENT (0 low-conf sites, 0 fallback rows, plots don't track geocode confidence) | **✅ STALENESS FIXED (v1.54)** — two-layer: (1) pre-filing readiness gate (`overdue_basis_feeds` → a Control-Center check "refresh before filing"), (2) snapshot stamps `feed_freshness_at_freeze` (auditable). Policy: FLAG + EXCLUDE, but staleness is *our* control so we surface it to refresh first. Test. **Remaining (latent):** geocode-`low_confidence` exclude-from-filing, missing-input `insufficient_data` flag, fallback degraded flag → tracked. |
| **T5** | Confidence Grade never enters the frozen snapshot payload | code-level | **✅ FIXED (v1.55)** — `confidence_grade`/`confidence_checks` added to csrd_e1 commodities → freezes with the snapshot. Test. |
| **T6** | `calc_settings`/`reporting_settings` changes: no 4-eyes; calc_settings unaudited | code-level | **✅ FIXED (v1.56)** — both config changes now route through `submit_or_apply_config` (`config_governance.py`): always audited, and governed by the same approval matrix as location edits. Two matrix actions seeded platform-default `requires_approval=FALSE` (`config_policy_actions_20260731`) → no UX change; an org toggles 4-eyes on per-action and `approvals.decide` dispatches `config.*` → `apply_config_change`. Integration test (default applies+audits; toggle-on routes to a 4-eyes request). |
| **T7** | iXBRL/XBRL regenerated live, never snapshotted (can drift from frozen pack) | code-level | **✅ FIXED (v1.55)** — build_ixbrl/build_xbrl_instance accept a `pack`; new `/report-snapshots/{id}.ixbrl` + `.xbrl` build from the FROZEN payload (filed bytes = frozen bytes) + UI buttons. Test. |
| **T8** | Same asset scoped differently in E1 vs Taxonomy (worst-hazard filter divergence) | code-level | **✅ FIXED (v1.57)** — climate-hazard scope extracted to `services/intelligence/hazard_scope.py`; E1 and Taxonomy adaptation both import the one `CLIMATE` set, and the Taxonomy report filters exposure on it (a geophysical worst-hazard site no longer counts as materially exposed under a climate objective). Parity test (shared-object identity + no non-climate hazard ever surfaces as exposed). |
| **T9** | FX treats NULL/blank currency as EUR (docstring says it never does) | code-level | **✅ FIXED (v1.57)** — `to_eur` now raises `FxError` on a None/blank currency (honours its own contract); the holdings router surfaces "market value without a currency" as an fx_error instead of guessing EUR at rate 1.0. A EUR-value-supplied line still needs no FX. Test covers None + blank. |
| **T10** | r²=0.40 floor triplicated as literals (no parity test) | partially addressed (all now on `r2_oos`, 0.40) | **✅ FIXED (v1.57)** — `fit_ranged_crop.py` imports `RANGED_PUBLISH_FLOOR` (single source of truth); a parity test pins the Python constant to the live DB calibration-view floor. |
| **T11** | No independent challenger for the supply euro; evidence concentration (Cocoa = 1 event; Coffee-BR drought `passed=false` live) | ✅ confirmed | **✅ DISCLOSURE FIXED (v1.57)** — verified live: the 3 failed validations (Coffee-BR/GT/PR) are all `price_claim_retired` and none publish a tier; Cocoa's single event is disclosed by the Confidence Grade (evidence_depth=Fair, honest_range="single-event uncertainty disclosed"). Both invariants locked by test (a failed validation never publishes 'backtested'; a single-event backtest discloses the caveat). **Roadmap gap (disclosed, not faked):** a genuinely independent challenger MODEL (a second method cross-checking the euro) is not built — tracked, not implied. |
| **T12** | No drift / re-validation trigger (validation is one-time) | code-level | **✅ FIXED (v1.57)** — `services/intelligence/revalidation.py` flags published calibrations whose training window is ≥3y behind the reporting year (an honesty constant); surfaced as Control-Center check `calibrations_current` (flags Cocoa CI/GH, trained thru 2020). Never auto-retires. Test. |
| **T13** | Geophysical: ESHM20 fallback rows labelled `eshm20_pga`; EMSC EU-only; USGS/GEM not wired | ✅ confirmed | **✅ FIXED (v1.57)** — adapter tags the raster vs the zone approximation distinctly (`eshm20_pga` vs `eshm20_zone_approx`, quality_flag 0/1); migration `seismic_provenance_20260801` relabelled all 11,325 historical rows honestly. EU-only coverage (global USGS/GEM not wired) already disclosed in the feed registry — a **disclosed roadmap gap**, not faked. |

## The 7 cross-cutting pillars (what an auditor probes beyond the linear pipeline)

Lineage · uncertainty propagation · reproducibility · **fail-safe** · drift monitoring · independent
challenger · invariant tests. The audit found concrete gaps in each; F1/F2/Fab/Reg + the tier-2 batch
close them progressively.

## What shipped this pass (2026-07-31)

- **F2** out-of-sample gate (retires Durum-wheat-ES + Wheat-IR honestly) + regression test.
- **F1** score-lane filter on the 4 unfiltered views + an invariant test over *all* physical-risk views.
- Deleted the `np.random` flood fabricator + a guard test forbidding random generators in ingestion.
- Relabelled the golden-source registry + the investor slide to what actually lands (`maturity` field).

## Tier-2 close-out (2026-08-01)

T1–T7 all shipped. **T4** partially: staleness wired (two-layer); geocode-`low_confidence` /
missing-input / fallback flags remain latent (tracked as T4b). Config governance (**T6**) closes the
last tier-2 item — calc/reporting-basis changes are audited and 4-eyes-governable.

## Tier-3 close-out (2026-08-01)

**T8–T13 all shipped**, plus the append-only regression test and the single r²-floor constant:

- **T10** — one r²-floor constant (fit script imports it) + DB-vs-Python parity test.
- **T9** — a blank currency is a surfaced FX error, never assumed EUR.
- **App-pillar** — `canonical_scores` UPDATE/DELETE both proven blocked by regression test.
- **T13** — ESHM20 raster vs zone-approximation tagged distinctly; 11,325 historical rows relabelled.
- **T8** — E1 and Taxonomy adaptation share one `CLIMATE` scope (can't diverge).
- **T12** — calibration re-validation control (flags training windows ≥3y stale) in the Control Center.
- **T11** — evidence-concentration honesty locked by test (failed validations never publish; single-event
  caveat disclosed). Two **disclosed roadmap gaps** (not faked): an independent challenger MODEL, and
  global (non-EU) seismic wiring.

**Remaining:** T4b — the three latent input-quality flags (geocode `low_confidence` exclude-from-filing,
missing-input `insufficient_data`, rule-based fallback degraded flag). All DB-verified latent today.
