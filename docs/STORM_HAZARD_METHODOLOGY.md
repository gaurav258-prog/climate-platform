# Storm Hazard Methodology — tropical cyclone wind decay

Companion to `VOLCANIC_HAZARD_METHODOLOGY.md` and the seismic physics doc. Storm is the
platform's third distinct hazard shape: not a fixed point (seismic epicentre, volcano vent) and
not a smooth continuous field (heat/drought) — a tropical cyclone is a **moving track**, a
sequence of positions each carrying its own wind field. **Governing rule, unchanged: we do not
ship a figure we cannot reproduce against a real event, and we disclose every approximation.**

## 1. The track problem, and why no new architecture was needed

A storm's hazard footprint sweeps across the map as it moves. Rather than invent new machinery,
this reuses a pattern the platform already has: `scripts/score_seismic_event.py` takes the **MAX**
intensity over every nearby event when an earthquake sequence has multiple aftershocks. A storm
track is scored the identical way — every 6-hourly IBTrACS observation is treated as its own
"event," the wind-decay physics is evaluated at each one, and each H3 cell keeps the highest
hazard it experienced from ANY point along the track. `scripts/score_storm_event.py` mirrors
`score_seismic_event.py`'s structure line-for-line in this respect.

## 2. Data source

**IBTrACS (NOAA/NCEI)** — confirmed live via direct HTTPS, no auth:
`https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NA.list.v04r01.csv`
(North Atlantic basin; other basins at the same path, e.g. `ibtracs.WP.list.v04r01.csv` for West
Pacific typhoons). Real columns confirmed by direct pull: `SID` (IBTrACS's own storm identifier —
**not** the NHC "AL152017"-style label; Hurricane Maria's real SID is `2017260N12310`, confirmed
live), `NAME`, `ISO_TIME`, `LAT`, `LON`, `USA_WIND` (max sustained wind, knots), `USA_PRES`
(central pressure, mb), `USA_RMW` (radius of maximum winds, **nautical miles**), `USA_SSHS`
(Saffir-Simpson category, -1 to 5). This is the ground-truth track catalog, the same tier as GVP
for volcanoes or EMSC/USGS for seismic.

**No live/near-real-time equivalent exists in this same no-auth style** — NHC's real-time
advisories aren't a clean machine-readable historical-format feed. Historical-only, same
limitation class as volcanic's GVP-catalog-only gap.

## 3. Scoring methodology

**Wind decay: Modified Rankine Vortex** — a standard, named tropical-cyclone wind-field model
(not invented for this project, same posture as seismic's Bakun & Wentworth IPE and volcanic's
proximal/ashfall decay):
```
V(r) = Vmax                    for r <= Rmax
V(r) = Vmax * (Rmax / r) ** x   for r > Rmax
```
`x = 0.5` — a commonly-cited mid-range decay exponent in the cyclone literature (values ~0.4–0.6
appear across studies). A single stated value, not fitted to Maria specifically.

**Rmax (radius of maximum winds)**: uses IBTrACS's real `USA_RMW` value when populated for a
track point (confirmed populated for Maria's Puerto Rico approach: 5–18 nautical miles, i.e.
~9–33km, tightening as the storm intensified to Category 5 and widening slightly as it weakened
crossing the island) — falls back to a category-scaled default (`ml/scoring/storm_physics.py`'s
`default_rmax_km`) when missing, same fallback posture as volcanic's `vei_to_zone_radii`. The
`shap_factors.rmax_source` field on every score row records which was used.

**Wind speed → 0–100 score**: piecewise-linear interpolation across Saffir-Simpson-referenced
anchor points (tropical storm force ~34kt → score 15; Category 5 ~137kt+ → score 95–100). Named
thresholds, not a fitted curve.

## 4. Backtest target: Hurricane Maria, September 2017 (Puerto Rico) — IBTrACS SID `2017260N12310`

Chosen for the same dual banking+agriculture reason Fuego was chosen for volcanic:
- **Banking**: NOAA/NCEI's official estimate — **~$90bn total damage** (3rd-costliest US
  hurricane on record), ~80% of Puerto Rico's electrical grid destroyed. Real San Juan
  infrastructure narrative for Meridian Bank.
- **Agriculture**: Puerto Rico Dept. of Agriculture — **~$780M total agricultural loss, ~80% of
  the island's total crop value destroyed**; separately, 18 million coffee trees destroyed
  (banana/plantain hit hardest of all crops). Puerto Rico coffee (Cordillera Central — Adjuntas,
  Yauco, Lares) is a real, small origin — a natural bolt-on to the existing "Coffee" commodity,
  the same move made for Guatemala under volcanic.

### 4.1 Banking check — spatial discrimination (`scripts/backtest_storm.py`)

| Site | Distance from track | Score | Driver |
|---|---|---|---|
| San Juan (capital, severe direct hit) | 31.4 km | 75.7 | 115kt, Category 4 |
| Cabo Rojo (SW tip, farther from the eyewall) | 59.2 km | 43.8 | 95kt, Category 2 |

**Verdict: correct.** San Juan, which sat closer to Maria's eyewall and took the more severe
direct hit, scores meaningfully higher than Cabo Rojo, at the island's southwest tip.

### 4.2 Agriculture check — Puerto Rico coffee vs Hurricane Maria 2017

**The disclosed limitation, carried over from Guatemala's volcanic backtest:** "Coffee" is ONE
global commodity — Brazil's drought calibration (`sensitivity=0.45`, `global_share=0.35`) is the
only fitted coefficient the schema has. Folding Puerto Rico's storm hazard under the same
commodity means the **live product** prices it using Brazil's much larger world share. This
script reports both numbers:

| | global_share used | yield-shock | price-move | €COGS-at-risk (P50) |
|---|---|---|---|---|
| (a) Live model (borrows Brazil's share) | 0.35 | 32.8% | 24.5% | €0.80m |
| (b) Origin-specific (Puerto Rico's real, tiny share) | ~0.0005 | 32.8% | ~0.0% | €0.11m |

**Real anchor, and an honest gap versus Guatemala's backtest:** unlike Anacafé's clean
coffee-specific "~0.9% of national production" figure for Fuego, Puerto Rico's Dept. of
Agriculture numbers are **economy-wide** (~$780M / 80% of total crop value, dominated by
banana/plantain losses, not coffee specifically). The only coffee-specific figure found — 18
million trees destroyed — is a real, sourced quantity but not convertible to a clean
percent-of-production anchor. **This backtest's agriculture side is therefore weaker and more
qualitative than Guatemala's or the cocoa/coffee climate backtests — stated plainly, not smoothed
over.** Puerto Rico's plot stays `indicative`, not added to `BACKTESTED`.

## 5. Known limitations (stated up front)

- **Historical-only data** — no live/near-real-time storm feed in this no-auth style, same class
  of gap as volcanic's GVP-only catalog.
- **Single decay exponent** (`x=0.5`) — a literature-typical value, not fitted to Maria.
- **Rmax fallback** — category-scaled default when IBTrACS's real RMW is missing for a track point.
- **Shared-commodity limitation** (§4.2) — the same disclosed gap Guatemala's volcanic coffee
  plot carries, now shared by a third origin under one Coffee line item.
- **No coffee-specific national-loss anchor for Maria** — the weakest link in this backtest,
  named explicitly rather than papered over with an approximate number.
- **IBTrACS SID vs. NHC label**: Hurricane Maria's real IBTrACS identifier is `2017260N12310`,
  not the NHC Atlantic-basin label `AL152017` — worth remembering if extending to another storm,
  since the two naming conventions are easy to conflate.

## 6. Files

- `ml/scoring/storm_physics.py` — Modified Rankine Vortex wind decay + Saffir-Simpson-referenced
  0–100 conversion + category-scaled Rmax fallback.
- `scripts/ingest_ibtracs_storm.py` — IBTrACS CSV → `storm_events`.
- `scripts/score_storm_event.py` — physics → `canonical_scores` (`hazard_type='storm'`), mirrors
  `scripts/score_seismic_event.py`'s max-over-multiple-events pattern.
- `scripts/wire_puerto_rico_storm_demo.py` — Puerto Rico coffee plot under the existing Coffee
  commodity.
- `scripts/backtest_storm.py` — the checks in §4.1/§4.2 above.
- `scripts/record_ag_validation.py` — persists the Maria result into `sc_model_validation`
  (surfaced on the Models & validation page).
