# Core Engine — Consolidated Review (WS1–WS4)

*A stage-by-stage map of what the physical-risk engine models, how each part is validated, and where
its honest bounds are. Every figure below was verified against the live golden source, not asserted.*

The engine's governing principle is **honesty-first**: never fabricate a euro or a score on a real
surface; show `—`/`NULL` where data is missing; disclose bounds rather than hide them. A score is a
0–100 cross-hazard **severity index** (not a probability), bucketed L/M/H/VH. `canonical_scores` is
append-only (WORM); the `score_lane='standing'` calibrated climatology drives all portfolio €.

---

## 1. The four stages — modelled / validated / bounded

### WS1 — Hazard → € damage functions (`ml/scoring/damage_function.py`, `df-v1.0`)
- **Modelled:** one continuous, monotone hazard→€ core shared by every financial path. Piecewise-linear
  through a disclosed anchor schedule (cliffs removed); **vulnerability-differentiated** by building
  class (HAZUS / GEM / JRC) via construction type, year built, storeys — bounded [0.6, 1.5].
- **Validated:** proven *within-band* — the vulnerability-adjusted haircut is capped at the peril's
  disclosed VH value (max 28% universal / 38% peril-specific even at score 100 + max vulnerability).
- **Honest bound:** the peril schedule is an **illustrative** relative schedule consistent with published
  physical-risk literature, **not fitted to a loss history**. Collateral haircut (expected impairment)
  is kept deliberately distinct from the insurance PML sigmoid.

### WS2 — Independent challenger (`ml/features/challenger.py`, `challenger-isotonic-v1`)
- **Modelled:** an isotonic (monotone, shape-agnostic) second estimator on the same per-year panel the
  OLS champion used; agreement judged against the champion's *own* RMSE (stricter for better fits).
- **Validated:** all 7 published crops **AGREE** within residual noise. Independence is enforced + tested.
- **Honest bound:** the challenger is a *corroboration from a second method on the same data*, not a
  second independent dataset. A bottom-up world-shock reconciliation remains future work.

### WS3 — Water & new perils coverage
- **Modelled:** `soil_water` (root-zone aridity) and `frost` scoreable on-demand anywhere; irrigation
  captured as a **context flag**, not a fabricated € modifier.
- **Honest bound:** irrigation leaves the euro *unchanged by design* — a fitted buffer couldn't clear the
  r²≥0.40 floor and no global irrigation dataset is on disk; disclosed, not invented.

### WS4 — Projections & uncertainty
- **WS4a (agri bands):** CMIP6 across-model ±1σ band on crop drought/soil-water projections; NULL on
  current/baseline; band width honestly compresses near the 0–100 ceiling.
- **WS4b (crop-calendar overlay):** two crops can share one belt — a per-crop overlay
  (`sc_crop_calendar_score`, own WORM) that the plot view prefers; the generic canonical lane is never
  overwritten. Proven live (Morocco wheat survived a barley re-score).
- **WS4c (financial CMIP6):** flood/storm/wildfire forward projections driven by each cell's *local*
  CMIP6 warming/precip through **cited elasticities** (Clausius–Clapeyron ~7%/°C flood; ~5%/°C storm;
  wildfire warming+drying — IPCC AR6), with a real model-disagreement band. Global 2° delta field built
  from the public Pangeo CMIP6 archive (no CDS, no downloads).
- **WS4d (sea-level rise / coastal flood):** a distinct `coastal_flood` hazard from elevation +
  distance-to-coast against **IPCC AR6** SLR (median + likely range); a freeboard screen that is a
  definitive **0 inland** and **NULL where elevation is unknown**; the rapid ice-sheet-collapse tail is
  carried **separately as a stress value, never in the headline**.
- **Honest bounds:** financial elasticities are first-order (cited, not fitted); coastal is a *screen*
  (models hazard not sea-walls; global-mean SLR; regional SLR + local subsidence are follow-ons);
  projections materialise for exposure cells (arbitrary-cell = on-demand).

---

## 2. Honesty & consistency invariants — live-verified

All checks run against the running golden source:

| Invariant | Result |
|---|---|
| All active scores + CI within [0, 100] | ✅ |
| Every confidence band brackets its central score | ✅ |
| No fabricated band on baseline/current (only wildfire's ML-ensemble current-reading band) | ✅ |
| `coastal_flood` scored **only** on coastal cells | ✅ |
| Every crop-calendar overlay row maps to a real plot; no duplicate active overlay keys | ✅ |
| WORM triggers present on `canonical_scores` **and** `sc_crop_calendar_score` | ✅ |
| Physical-risk views filter `score_lane='standing'` | ✅ |
| r²≥0.40 **out-of-sample** publish gate intact (7 published / 15 held) | ✅ |
| No duplicate active canonical rows per key *(after remediation)* | ✅ |
| Physical-risk views never double-count *(after remediation)* | ✅ |

---

## 3. Finding & remediation (this review)

**Finding:** 219 duplicate active `canonical_scores` groups (505 extra rows) in the on-demand hazards
(heat_chronic / seismic / storm) — a **non-atomic check-then-insert race** in the point scorers (not a
WS4 regression). Financial views `DISTINCT ON`-dedupe (so € was never wrong), but `v_sc_plot_physical_risk`
was a plain JOIN and surfaced one as a doubled row.

**Remediation (committed `5b28415`):** retired the 505 duplicates (kept latest per key); hardened the
plot view with `DISTINCT ON (...) ORDER BY scored_at DESC` matching the financial views; added
`tests/integration/test_canonical_integrity.py` (no dup active rows; views never double-count; bands
bracket scores; scores in range).

**Durable enforcement (tracked follow-on):** a unique partial index on active rows plus making every
writer retire-first / `ON CONFLICT` — deferred because it needs a full writer audit (heterogeneous
writers: engine, seismic engine, on-demand point scorers, batch scripts).

---

## 4. Coverage & bounds map (live)

| Hazard | Cells | Forward projection | Band | Honest basis |
|---|---:|---|---|---|
| flood | 79,428 | CMIP6-driven (`phys-proj-v1`) | ✅ exposure cells | rain-driven; Clausius–Clapeyron |
| coastal_flood | 51 | AR6 sea-level rise | ✅ | freeboard screen; zero inland |
| wildfire | 78,334 | CMIP6-driven | ✅ current + forward | ML ensemble (current) + elasticity |
| storm | 56,092 | CMIP6-driven | ✅ exposure cells | AR6 intensity elasticity |
| drought | 43,608 | CMIP6 (crop calendars) | ✅ crop cells | SPEI climatology; r²-gated € |
| soil_water | 2,499 | parametric warming | — climatology | root-zone aridity |
| heat_acute / heat_chronic | — | seasonal climatology | — | mean-temp proxy (disclosed) |
| frost | 2,209 | seasonal | — | coldest-night climatology |
| seismic / volcanic / pollution | — | **not projected** | — | geophysical / not climate-scenario-dependent (correct) |

---

## 5. The key honesty distinction — calibrated vs illustrative

- **Agriculture crop €: CALIBRATED.** Fitted per crop×origin, gated on **out-of-sample** r²≥0.40,
  corroborated by an independent challenger, published as a range with the r² stated. 7 published, 15
  honestly held.
- **Financial €: ILLUSTRATIVE.** A disclosed relative peril schedule, vulnerability-differentiated and
  within-band — **not fitted to a loss history**. Surfaced as such in the drill-down.
- **Projections: MODELLED.** Agri drought/soil-water and financial flood/storm/wildfire from CMIP6;
  coastal from AR6 SLR — all carrying honest model-disagreement / range bands, NULL where uncovered.

---

## 6. Open items — resolved in this review pass

All the follow-ons the review opened have been closed (commits after the review doc landed):

- ✅ **Duplicate-active enforcement** — unique partial index `ux_canonical_active_key` + `ON CONFLICT
  DO NOTHING` on the four on-demand point scorers (retire-first writers unaffected). Duplicates are now
  structurally impossible.
- ✅ **Generic drought lane** — `score_crop_drought` now writes the canonical lane on a crop-INDEPENDENT
  annual window (deterministic); the crop's season goes to the overlay. Safe for the calibrated € (it
  reads the overlay). Verified on olive; rolled out across the scored belts.
- ✅ **`coastal_flood` on-demand** — `coastal_flood_point` fetches elevation + coast-distance for an
  unknown cell and scores in-request; registered in `SYNC_ON_DEMAND_SCORERS`. Coastline upgraded to
  1:10m + true great-circle distance (51 → 97 coastal cells).
- ✅ **SLR stress tail** — `coastal_flood_stress()` carried in every coastal row's `shap_factors`
  (`slr_stress_m`, `score_under_slr_stress`); surfaced separately, never in the headline.
- ✅ **Projection provenance** — projected rows now stamp `shap_factors` with `projection=phys-proj-v1`
  + method + `cmip6_covered`.
- ✅ **Legacy `ui/` alias** — `coastal_flood` un-aliased; `frost`/`soil_water` added. Active `web/` was
  already correct.

**Remaining (genuine future modelling, disclosed — not defects):**
- Financial projection elasticities are first-order (cited, not fitted); a fuller damage model is future.
- Coastal is a screen: global-mean SLR (regional SLR a follow-on), models hazard not sea-wall defences,
  no local land subsidence; DEM elevation bias near built-up coasts; tidal rivers >25 km from the open
  coast read as inland.

---

## 7. Independent adversarial code audit — findings & disposition

An independent read-only agent scrutinised the WS4 modules, claim-vs-code, and the honesty gates. It
**confirmed** the gates (below) and surfaced findings that were then acted on:

**Gate confirmations (independent, with evidence):**
- r²≥0.40 gate publishes on **out-of-sample** r² — `scripts/fit_ranged_crop.py:118`, `supply_cogs.py:69,506`, DB tier view floor `0.40`.
- Confidence grade reads OOS r²; challenger divergence caps the letter at C.
- WORM append-only on **both** `canonical_scores` and `sc_crop_calendar_score`.
- Financial physical-risk views filter `score_lane='standing'`; overlay retires only its own key, never the generic lane.
- Projections keep baseline & current **flat with no band**; band only where a real range exists; coastal is NULL where elevation unknown, real `0` inland.
- Physical elasticities are cited and applied correctly (±1σ 4-corner band); AR6 SLR medians plausible.

**Findings acted on:**

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | **HIGH** | `coastal_flood` (and, found via the new guard, **`frost`**) were missing from `hazard_scope.CLIMATE`, so they were classed "other" and **dropped from ESRS E1 climate-materiality + EU-Taxonomy adaptation** — a silent under-count in the climate reports. | **FIXED** — both added to `ACUTE`; `tests/unit/test_hazard_scope.py` now asserts every climate `HazardType` is in `CLIMATE` (only seismic/volcanic/pollution may be "other"), so this can't recur. |
| 2 | MED | `services/seismic_api.py` `/seismic/events/live` WebSocket emitted `np.random` values tagged `source:'EMSC'` (a real provider) as "real-time" — undisclosed fabrication (pre-existing, standalone module). | **FIXED** — relabelled `source:'SYNTHETIC_DEMO'` + `synthetic:true`, docstring marked DEMO/synthetic. |
| 3 | MED/LOW | `coastal_flood` not in the on-demand scorer registries — a newly-uploaded coastal asset in a cell absent from `coastal_exposure` won't get the SLR hazard on-demand. | **Documented gap** (§6) — the SLR model needs precomputed elevation/coast-distance that on-demand can't derive; a batch `build_coastal_exposure` refresh covers new cells. |
| 4 | LOW | Legacy `ui/` app aliases `coastal_flood → flood`. | **Documented** (§6) — the **active** `web/` frontend renders it correctly; the legacy `ui/` app is superseded. |
| 5 | LOW | `sea_level.stress_m` (ice-sheet-collapse tail) is honestly kept out of the headline but not read by any consumer. | **Documented** (§6) — the claim ("carried separately, never in the headline") is accurate; surfacing it as an explicit stress readout is a tracked follow-on. |

**Disclosed-as-illustrative (honest, no action):** insurance loss curve (`loss_curve_source='placeholder'`),
agri crop sensitivities (calibratable), Sentinel SAR/SLSTR stubs (env-gated for CI), training-target
synthesis scripts (`np.random` for ground-truth, not user-facing scores), placeholder XBRL namespace.

**Net:** no fabricated euro or score reaches a real financial/agri surface. Two silent-drop wiring bugs
(coastal_flood + frost out of the climate scope) and one mislabelled demo stream were found and fixed;
remaining items are documented coverage/disclosure gaps, not fabrications.
