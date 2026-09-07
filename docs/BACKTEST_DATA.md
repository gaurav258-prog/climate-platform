# Backtest data — status and runbook

## Update (2026-09-07): independent official targets are now reachable — and used

The two blockers below ("official footprints" and "feature backfill") are closed for the panel we already
hold. Three independent, authoritative targets were re-established and landed by script (no manual GIS):

| target | source | script | landed |
|---|---|---|---|
| Wildfire burnt area | EFFIS burnt-area mapping (JRC/Copernicus EMS), WFS `ms:modis.ba.poly`; bbox is LAT-first, CQL is refused, 500s on large boxes → quadrant split | `scripts/fetch_effis_burnt_area.py` | `data/wildfire_val/effis_*.geojson`, all 8 fires |
| Flood observed extent | Copernicus EMS rapid mapping `observedEventA` — dashboard API (`/backend/dashboard-api/public-activations/?code=`, ≈EMSR660+) with per-product layer JSON, and the S3 delineation vector packages for older activations; activations verified by AOI geometry + date, never by name | `scripts/fetch_ems_flood_footprints.py` | `data/flood_val/ems_*.geojson` (EMS-era events, 2013→) |
| Coastal extreme water level | NOAA CO-OPS verified monthly highest water levels, 2014-2023, per gauge vs MHHW/MSL datums | `scripts/fetch_coops_extremes.py` | `data/coastal_val/coops_monthly_extremes.csv` (234 gauges) |

Labels are applied at the panel's own resolution: an ERA5-Land 0.1° node counts as burned/flooded when the
official polygon intersects its grid box (testing only the ~0.7 km² node cell missed almost every scar).

**Wildfire — FAILS (`scripts/backtest_wildfire_effis.py`).** Live model (ERA5-Land fire weather + fuel, trained on
FIRMS hotspots), each of the 8 fires held out, judged on the EFFIS scars: pooled ROC-AUC **0.440**, AP 0.103
(base 0.122), rank ρ −0.07. Trained-and-judged on EFFIS: AUC 0.433. The FIRMS-on-FIRMS reference re-run on the
same panel: AUC 0.421 — the registry's 0.568 does not reproduce on the current panel either. Conclusion: day-of
fire weather does not locate where a fire burns; ignition and fuel-continuity data would be needed. Wildfire
stays SCREENING (taxonomy row + `model_registry.validation_note` updated with the number).

**Coastal — calibration check, not a skill claim (`scripts/backtest_coastal_coops.py`).** 169 CONUS gauges with
≥60 verified months. The generic `SURGE_ALLOWANCE_M = 2.0` m above MSL sits at the **80th percentile** of observed
10-year gauge maxima (median 1.43 m, p90 2.27 m; 20% of gauges saw more — Gulf of Maine tides, Boston, TX/LA
surge). Ranking: ρ = **−0.32** — the score carries elevation only, so it ranks flat low coasts high while
observed extremes peak on steep macro-tidal / surge coasts. Coastal stays SCREENING; a site-specific
extreme-water-level term (these gauges, or a global equivalent) is the disclosed gap.

**Wildfire REBUILT as a hazard climatology — passes (`scripts/backtest_wildfire_climatology.py`).** The failure above
was the wrong question (day-of weather cannot locate a burn). The scored lane is now a standing climatology:
Copernicus CEMS/ECMWF Fire Weather Index extreme-danger days 2006-2020 (EWDS `cems-fire-historical-v1`; the
account's EWDS terms of use were accepted 2026-09-07) × burnable-land fraction + C3S ESA-CCI burned-area history
2001-2019 (`satellite-fire-burned-area`, ends 2019). Fixed formula, no fitted parameters. Target held out in
TIME: all 41,513 EFFIS scars 2022-2024 in Europe (`scripts/fetch_effis_europe.py`), case-control vs random
burnable land. Weather×fuel alone: AUC 0.679, ρ 0.22 (below gate). With history: **AUC 0.757, High+ lift 2.2×,
ρ 0.367** — passes the 0.35 floor, marginally. History alone: AUC 0.795, ρ 0.48 — the burn record carries most
of the skill (in-domain, the landslide/LHASA caveat); the weather term is kept because it is the climate driver
and the only path to a warming-shifted projection. Wildfire → CALIBRATED, Europe-validated (screen elsewhere).
The old day-of model stays registered as a nowcast signal, retired as the address score.

**Flood — real but modest skill, below the calibration gate (`scripts/backtest_flood_ems.py`).** EMS observed
extents landed for the 6 EMS-era events (Ahr 2021 EMSR517, Spain DANA 2019 EMSR388, Storm Alex 2020 EMSR467,
Emilia-Romagna 2023 EMSR664, Storm Boris 2024 EMSR756+757, Valencia 2024 EMSR773; 2013/2014/2016 activations
exist but their old-format packages ship shapefiles without GeoJSON — not yet parsed). Production model
(trained on corridor labels), each event held out, judged on the EMS extent: pooled ROC-AUC **0.677**, AP 0.161
(base 0.084, ~2×), rank ρ 0.17; 5 of 6 events 0.71-0.85, the Storm Alex flash flood 0.42. Trained-and-judged on
EMS extents: AUC 0.733, AP 0.194 — the official labels are cleaner than the corridors (Storm Boris 0.48→0.80).
Riverine skill is real; flash floods are not resolved by 0.1° daily ERA5-Land. Flood stays SCREENING: ρ is far
below the 0.35 ranking floor (a rare binary target at 8% base rate caps ρ, but the gate is the gate).


---

## Update (2026-06-27): multi-event model now validated

The single-event model did not generalise — scored two unseen floods (2002, 2013)
at random (out-of-event AUC 0.47). We then fetched **8 real European floods**
(2002–2024) from CDS, built features, labelled documented corridors, and ran a
**leave-one-event-out** backtest (`scripts/build_multievent_flood.py`):

| held-out flood | AUC | AP | base |
|---|---|---|---|
| 2002 Elbe | 0.616 | 0.079 | 0.069 |
| 2005 Alpine | 0.886 | 0.614 | 0.127 |
| 2010 Vistula | 0.660 | 0.193 | 0.143 |
| 2013 Danube | 0.621 | 0.089 | 0.076 |
| 2014 Sava | 0.592 | 0.157 | 0.137 |
| 2016 Seine | 0.527 | 0.092 | 0.090 |
| 2021 Rhine/Ahr | 0.803 | 0.200 | 0.061 |
| 2024 Storm Boris | 0.677 | 0.229 | 0.104 |
| **POOLED** | **0.645** | **0.203** | 0.102 |

Pooled LOEO **AUC 0.645, AP 0.203 (2× base rate)** — real but modest forecasting
skill, validated on events held out entirely. The final model
(`flood-multievent-v…`, trained on all 8) is registered active with these honest
metrics. Remaining caveats: corridor labels are approximate; CDS fetch is the
cost to add more events; deploying it to live scoring needs the same feature
computation in the pipeline. Below is the original analysis that led here.

---


The flood and wildfire models are each trained on **one** event with **approximate**
labels, so their skill cannot be honestly backtested (see `scripts/backtest_hazard.py`:
ROC-AUC ~0.99 but Average-Precision ~0.04–0.05, recall@K ~0.07–0.11, and no
out-of-event test is possible). A real backtest needs **multiple independent
labeled events across years**. This documents exactly what that requires and what
is currently blocking it — established by probing, not assumption.

## What exists today

| | Flood | Wildfire |
|---|---|---|
| Labeled event(s) | 1 — Rhine/Ahr, Jul 2021 | 1 — Gironde, Jul 2022 |
| Label source | `fallback_emsr517_approx` | `fallback_effis_2022_approx` |
| Features cover | 2021-07-05 → 15 | 2022-07-10 → 22 |
| Labels cover | 2021-07-14/15 only | 2022-07-12 → 17 only |

## What a real backtest needs (and the two blockers)

To label event *E* on date *D* you need: (1) the official footprint of *E* → the
H3 cells that flooded/burned, and (2) the model features for *D* in
`ml_features_*`. Both are blocked right now:

**Blocker 1 — official footprints.** `load_ground_truth_labels.py` targets the
Copernicus EMS and EFFIS WFS endpoints. Probed 2026-06-27: the sites resolve
(`emergency.copernicus.eu` 200, `effis.jrc.ec.europa.eu` 302, CDS 200) but the
WFS/feature endpoints return **no geometry** — which is why the existing labels
fell back to hardcoded polygons. Both services have migrated (EFFIS → GWIS; EMS →
a per-activation download portal). The current correct access path must be
re-established before real multi-event footprints can be pulled.

**Blocker 2 — feature backfill.** Even with footprints, features for each new
event date must be built from ERA5/GloFAS via the Copernicus CDS. Credentials are
present (`~/.cdsapirc`) and `scripts/backfill_historical.py` works, but it is
~168 CDS requests per day and the CDS is a queue — a single multi-day event is
hours, a multi-event catalog is days. This is not a single-session task.

## Runbook (when the data effort is funded)

1. **Re-establish footprint access.** Confirm the current Copernicus EMS download
   API (per EMSR activation) and the EFFIS/GWIS burnt-area product. Pick ~8–12
   flood EMSR activations and ~6–10 EFFIS fire seasons spanning ≥10 years.
2. **Extend the catalog.** Generalise the two hardcoded events in
   `backfill_historical.py` into a catalog (id, hazard, date range, region bbox,
   footprint source ref).
3. **Backfill features.** Run `backfill_historical.py` over the catalog dates
   (long-running CDS job) → `satellite_observations` → feature pipeline →
   `ml_features_*`.
4. **Label.** Extend `load_ground_truth_labels.py` to iterate the catalog, fetch
   each footprint, convert to H3, and set `flood_occurred`/`fire_occurred`.
5. **Backtest for real.** Run a **temporal** split — train on pre-2020 events,
   test on held-out later events — and report Average-Precision and recall@K on
   events the model has never seen. That is the number that establishes (or
   refutes) forecasting skill.

## Honest position until then

`model_registry.validation_note` records, per model, that the score is validated
on a single proxy-labeled event and that forecasting skill is untested. The UI
surfaces the Average-Precision and that caveat next to every live number. Nothing
downstream should quote the ROC-AUC as the model's skill.
