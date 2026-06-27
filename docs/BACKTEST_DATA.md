# Backtest data — status and runbook

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
