# Backtest data — status and runbook

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
