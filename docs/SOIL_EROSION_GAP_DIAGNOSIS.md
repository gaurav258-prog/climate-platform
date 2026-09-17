# Soil erosion — validation-gap diagnosis (GloSEM vs EUSEDcollab / GRILSS)

**Question it answers:** `soil_erosion` (GloSEM point channel, `ml/scoring/soil_erosion_point.py`) backtests
against two independent observed sediment-yield targets came back far below the 0.35 rank-correlation gate —
EUSEDcollab raw ρ = 0.089 (n=204), GRILSS raw ρ = 0.078 (n=670). Applying the Boyce (1975) sediment-delivery-
ratio (SDR) correction (`ml/scoring/soil_erosion_sdr.py`) moved these only slightly (0.109 / 0.120). This doc
investigates *why* the gap is so large, using the real (predicted, observed) arrays pulled directly from the
raster and the raw validation data — not speculation. **No production scoring, tier, or registered validator
was changed.** All numbers below were computed in scratchpad scripts (not committed) that sample
`data/soil_erosion/GloSEM.tif` directly and load `data/erosion_val/*` exactly as the registered validators do;
the raw-point-sample numbers reproduce the registered ρ values (0.097/0.076 vs 0.089/0.078 — the small gap is
score-bucket rounding in the registered path, not a discrepancy).

## Hypotheses tested, in order

### 1. Point-sampling noise — CONFIRMED as a real, substantial driver

Neither validator areally-averages GloSEM over the catchment polygon; both sample the raster at a single
(lat, lon) — the gauging station for EUSEDcollab, the dam coordinate for GRILSS. EUSEDcollab ships no
catchment boundaries (can't test areal averaging there). **GRILSS does** — `Vector_data/shapefile/
catchments_shapefile/GRILSS_catchments_v1.2.shp` has 1,013 actual drainage-basin polygons keyed by `GRILSS
RID`, which joins directly to the sedimentation table.

Zonal-mean GloSEM (mean of all raster pixels inside each catchment polygon) vs point-sample, on the *exact
same* 668 catchments where both are available:

| Sampling | ρ | p | n |
|---|---|---|---|
| Point (registered method) | 0.076 | 0.051 | 668 |
| Zonal mean (catchment polygon) | **0.164** | **2.0e-5** | 668 |

Zonal sampling also recovers coverage for catchments the point-sample missed entirely (raster edge/nodata at
the exact dam pixel but valid pixels elsewhere in the basin): 1,226 of 1,231 filtered GRILSS rows get a zonal
value vs 668 for point-sample. On the full zonal set, zonal+SDR (each catchment's own polygon area) reaches
ρ = 0.157 (p = 3.1e-8) vs the registered point+SDR ρ = 0.120.

**Point-sampling more than doubles the noise floor relative to zonal averaging on GRILSS** — this is the
single largest, most concrete, most fixable factor identified. It is not, however, enough on its own: even
zonal+SDR (0.157–0.164) remains well below the 0.35 gate.

### 2. Distributional / outlier issues — a real secondary effect, opposite in each dataset

- **GRILSS**: trimming the most extreme 10% of observed+predicted values (by quantile) raises ρ from 0.076 to
  0.19 — a few extreme reservoirs (mostly tiny catchments <1 km² where the volumetric proxy's denominator
  blows up, e.g. "Adebra night storage", catchment 0.008 km², proxy 1,369 m³ ha⁻¹ yr⁻¹) are actively
  suppressing the correlation. Log-log Pearson on GRILSS is even weaker than raw Spearman (r=0.044, p=0.26) —
  no real log-linear signal, consistent with a genuinely noisy/scattered relationship rather than a nonlinear
  one being mis-tested by rank correlation.
- **EUSEDcollab**: the opposite — trimming outliers makes ρ *worse* (0.097 → -0.09 at 10% trim). The weak
  positive raw signal is carried almost entirely by a handful of extreme, non-Danish catchments (see §5). The
  log-log Pearson on the full set is notably higher than raw Spearman (r=0.29, p=2e-5 vs ρ=0.097, p=0.17) —
  the underlying log-log relationship is real but Spearman's local rank sensitivity is drowned out by noise in
  the dominant bulk of the sample (see §5), which is a distributional artifact, not a sign the SDR-style
  correction is wrong.

### 3. Temporal mismatch — RULED OUT as a driver

GloSEM 1.3 is the "scenario 2019" present-day layer (`scripts/fetch_soil_erosion.py`). If temporal mismatch
were the story, catchments whose observation window overlaps ~2019 should score noticeably better.

- EUSEDcollab: measurement end-year spans 1999–2021 (median 2009). Restricting to end-year ≥ 2010 or ≥ 2015
  (closer to GloSEM's reference year) does **not** improve ρ (2010+: ρ=0.11 n=15; 2015+: ρ=-0.03 n=13; both
  small-n but showing no trend toward better agreement near 2019).
  the pre-2010 bulk actually has slightly *worse* ρ (-0.04) but 2010+ isn't meaningfully better either.
- GRILSS: observation end-year spans 1885–2023 (median 2003), durations 1–296 years. Splitting at end-year
  2000 or 2010, the *older* half correlates *better* (end<2000: ρ=0.165, p=0.005, n=286) than the half ending
  after 2000 (ρ=0.036, p=0.48, n=382) — the **opposite** of what a temporal-mismatch story predicts.

Land-use change since older records is a real phenomenon in principle, but it is not what the data shows here
— overlap-with-2019 does not predict agreement. Ruled out as a primary driver.

### 4. Land-use / cropland-only masking mismatch — plausible in principle, not confirmed by the data

GloSEM's own docstring is explicit: Borrelli et al.'s product estimates "soil displacement **in croplands** by
water erosion" — it is a cropland-specific RUSLE product, not an all-land-cover estimate. EUSEDcollab's
metadata (`ALL_METADATA.csv`) carries `Land use: % agriculture` per catchment (populated for 113/204 usable
catchments; the rest are `NaN`, not zero).

| Subset | n | ρ | p |
|---|---|---|---|
| % agriculture ≥ 0 (any known value) | 113 | 0.133 | 0.16 |
| % agriculture ≥ 50 | 95 | 0.038 | 0.71 |
| % agriculture ≥ 80 | 36 | 0.164 | 0.34 |
| % agriculture unknown | 91 | 0.069 | 0.51 |

Restricting to high-cropland catchments does not produce a clean, monotonic improvement (≥50% is *worse* than
the unfiltered set; ≥80% is similar to the unfiltered ρ but not significant at n=36). GRILSS carries no
land-cover field at all, so this can't be cross-checked there. **The mechanism is real and documented, but the
metadata available doesn't show it explaining a meaningful share of the gap** — treated as unconfirmed, not
ruled in.

### 5. Sample composition — a genuine, previously undocumented confound in EUSEDcollab

185 of 204 usable EUSEDcollab catchments (91%) are Danish — flat, low-relief, glacial-till agricultural
catchments, all "Monthly data" type. Within that dominant Danish subset alone, ρ = **-0.081** (p=0.28, n=185)
— essentially zero-to-negative. The weak positive headline ρ (0.097) is carried entirely by the 19 non-Danish
catchments (Belgium, Spain, Poland, etc.), which alone show ρ=0.19 (p=0.44, n=19 — not significant on its own,
but directionally consistent and much larger in magnitude).

The Danish subset also shows a striking, consistent **~20x gross-over-observed gap**: mean GloSEM predicted
rate 1.17 t ha⁻¹ yr⁻¹ vs mean observed SSY 0.055 t ha⁻¹ yr⁻¹ — far beyond what the Boyce SDR curve predicts for
these catchment sizes (drainage areas mostly 100s–10,000s ha → SDR ≈ 0.4–0.6, i.e. only a ~2x reduction
expected, not ~20x). This is consistent with GloSEM's RUSLE inputs being poorly discriminating on genuinely
flat terrain (near-zero LS-factor everywhere means the model has little basis to rank low-relief catchments
against each other) plus Danish farming practice (buffer strips, reduced tillage, tile drainage rather than
overland flow) suppressing delivered sediment far more than a global area-only SDR curve captures. The
disclosed "sample skews heavily Danish" note in the validator docstring undersells how much this single
homogeneous, low-signal subgroup dominates and flattens the headline number — worth being more explicit about.

### 6. Unit/scale sanity check — RULED OUT, no gross bug

Spot-checked (predicted, observed) pairs side by side for both datasets:

- EUSEDcollab: GloSEM 0.26–14.5 t ha⁻¹ yr⁻¹ vs observed SSY 0.02–1.03 t ha⁻¹ yr⁻¹ in a representative sample —
  same units, same order-of-magnitude family, ratio 5–50x (plausible gross-vs-net, not a units bug).
- GRILSS: GloSEM (t ha⁻¹ yr⁻¹, mass) vs the volumetric SSY proxy (m³ ha⁻¹ yr⁻¹) are, as disclosed in the
  validator's own docstring, different physical quantities related by sediment bulk density (~1.0–1.6 t/m³) —
  a spot check of 10 random reservoirs shows values in the same broad range (single to low-hundreds per
  hectare-year) once that ~1–1.6x factor is allowed for, except for a handful of tiny-catchment outliers
  already identified in §2. No gross unit or scale error.

## Bottom line

No single hypothesis fully explains the gap; three real, quantified, compounding factors were found, in
order of impact:

1. **Point-sampling a highly heterogeneous raster at one pixel is a real noise source** — zonal averaging
   over GRILSS's actual catchment polygons more than doubles ρ on an identical sample (0.076 → 0.164), the
   single largest lever found. (Not testable for EUSEDcollab — no catchment polygons shipped.)
2. **A few extreme observations dominate/suppress each dataset differently** — GRILSS is hurt by outliers
   (trimming helps, 0.076 → 0.19); EUSEDcollab's weak signal is instead *carried* by its few non-Danish,
   non-dominant-subgroup catchments while the dominant 91%-Danish, flat-terrain subgroup shows no signal at
   all (ρ=-0.08).
3. **Sample composition (§5) compounds with cropland-specificity (§4)**: Denmark's flat-till, buffer-stripped
   agricultural catchments are exactly the case where a cropland-RUSLE model's slope-driven ranking has the
   least basis to discriminate, and where local water-management practice (not captured by an area-only SDR
   curve) suppresses delivered sediment far more than elsewhere.

Temporal mismatch (§3) and a gross unit/scale bug (§6) are both ruled out by the actual data. Cropland-masking
(§4) is a real, documented property of GloSEM but the EUSEDcollab land-use metadata doesn't show it explaining
a material share of the gap on its own.

Even combining the best-supported fix (zonal averaging, tested end-to-end on GRILSS) with the SDR correction
only reaches ρ ≈ 0.16 — well short of 0.35. **The gate is not cleared, and nothing here justifies promoting
`soil_erosion` out of screening tier.** This is a case where GloSEM's rank-skill against catchment-integrated
sediment yield is genuinely weak at these catchment scales, not primarily a fixable methodology bug in our
validators.

## What was and wasn't changed

- No production file (`ml/scoring/soil_erosion_point.py`, `ml/scoring/soil_erosion_sdr.py`,
  `services/validation/validators/soil_erosion_eusedcollab.py`,
  `services/validation/validators/soil_erosion_grilss.py`, `core/hazard_taxonomy.py`) was modified.
  `soil_erosion` remains screening tier, unchanged.
- The zonal-averaging test (§1) was run in an ad hoc scratchpad script (geopandas + `rasterio.mask`, not
  committed) reading the GRILSS catchment shapefile directly — it deliberately bypasses the production
  process-isolated raster sampler (`services/geo/raster_sampler.py`), which currently only exposes point
  `sample`/`window` ops, not polygon masking. Wiring a real zonal-mean capability into the registered GRILSS
  validator would require extending that sampler with a process-isolated polygon-mask op (and adding
  `geopandas` as a declared dependency — currently used ad hoc in one script,
  `scripts/ingest_natura2000.py`, not in `pyproject.toml`). Not done here: it doesn't clear the gate even
  where tested, so it would add real code/architecture surface for a number that's still an honest fail.
