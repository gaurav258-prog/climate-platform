# Pollution Hazard Methodology — WHO AQG-anchored air-quality scoring

Companion to `STORM_HAZARD_METHODOLOGY.md` and `VOLCANIC_HAZARD_METHODOLOGY.md`. Pollution is a
categorically different kind of risk from every other hazard here: it measures **chronic health
exposure to people**, not structural/crop damage — kept as its own `hazard_type='pollution'`,
never blended into the damage-risk score. **Governing rule, unchanged: we do not ship a figure we
cannot reproduce against a real event, and we disclose every approximation.**

## 1. Scoring: WHO Global Air Quality Guidelines (2021), not an arbitrary 0–100 scale

`ml/scoring/pollution_aqi.py` anchors every breakpoint to the WHO 2021 Global Air Quality
Guidelines — the current international reference (supersedes the 2005 guidelines) — Table 0.1 /
NBK574582, the OFFICIAL published numbers, verified via the WHO document itself (not estimated):

| Pollutant | Averaging | AQG | IT-4 | IT-3 | IT-2 | IT-1 |
|---|---|---|---|---|---|---|
| PM2.5 | 24-hour | 15 | 25 | 37.5 | 50 | 75 |
| PM10  | 24-hour | 45 | 50 | 75  | 100 | 150 |
| NO2   | 24-hour | 25 | — | —   | 50  | 120 |
| SO2   | 24-hour | 40 | — | —   | 50  | 125 |
| O3    | 8-hour  | 100 | — | —  | 120 | 160 |

(all µg/m³). 24-hour/8-hour values are used rather than annual means, since this scores
current/forecast conditions at a point in time, not chronic long-run exposure. Each pollutant maps
onto its own 0–100 sub-score by linear interpolation between these named breakpoints (AQG→20,
IT-1→100 for the 5-point scale; AQG→33, IT-1→100 for the 3-point scale), capped at 100 beyond
IT-1. The **overall score is the MAX across available pollutant sub-scores** — the standard
multi-pollutant AQI convention (US EPA AQI, EU CAQI): the worst pollutant governs, never averaged
away behind cleaner ones.

## 2. Scope decision: PM2.5/PM10 only for v0 — disclosed, not hidden

CAMS's `cams-global-atmospheric-composition-forecasts` dataset (via ADS) only exposes PM2.5/PM10
as simple single-level surface concentrations. NO2/SO2/O3 exist in the same dataset, but **only**
as multi-level mixing ratios (kg/kg) requiring a pressure-level pick (confirmed via the dataset's
own `form.json` — no single-level surface product for them) plus density conversion using
co-retrieved temperature/pressure. Real extra work for pollutants that are not the driver in
either backtest target below — Delhi's smog and California's wildfire smoke are both
PM-dominated events, same as most real-world AQI alerts. `pollution_aqi.py` already accepts
NO2/SO2/O3 as optional and simply omits them from the max-of-sub-scores when absent, so adding
them later is additive, not a rework. Same "disclose the gap" convention as frost (blocked on
CDS) and MIROVA (no public API) elsewhere in this project.

## 3. Two CAMS products, deliberately — a real bug caught and fixed via live testing

`ml/features/pollution_cams.py` exposes **two** fetch functions, not one:

- `fetch_cams_forecast` — the live/near-real-time forecast archive. Right for "what's the air
  like right now" on-demand lookups (`scripts/score_point_gridded_on_demand.py`'s
  `run_pollution_lookup`).
- `fetch_cams_reanalysis` (CAMS EAC4) — assimilates real observations after the fact, same role
  ERA5-Land reanalysis plays for flood/heat/drought. Right for reconstructing a PAST event
  (`scripts/backtest_pollution.py`).

**Why two, not one — a genuine miss found via honest ground-truth comparison, not assumed away:**
scoring the 2020 California wildfire smoke event via the **forecast** archive initially returned
PM2.5 ~1.5–24µg/m³ against a real OpenAQ station reading of ~129µg/m³ — a near-total miss
(model scored **L**, the event was genuinely severe). Re-running the identical point/day through
**EAC4 reanalysis** instead returned 45–70µg/m³ — same order of magnitude, correctly severe. The
forecast product is a pure forward model with no benefit of hindsight-observation-assimilation;
for a date in the past, that's the wrong tool, exactly the same reasoning this project already
applies by using ERA5-Land *reanalysis* (not a forecast archive) everywhere else. **Rule: use
`fetch_cams_reanalysis` for any date in the past, `fetch_cams_forecast` only for "today."**

**Second bug, same root cause (publish lag), found the same way ERA5Adapter already handles
it:** requesting `fetch_cams_forecast` for `date.today()` is genuinely rejected by ADS
("Request has not produced a valid combination of values") until that day's 00:00 UTC run has
published — confirmed live (today rejected, yesterday and 2 days ago both accepted). Fixed with
a 1-day margin (`date.today() - timedelta(days=1)`), same class of fix as `ERA5Adapter`'s "ERA5
lags ~5 days; default to 7 days ago."

## 4. OpenAQ — ground-truth calibration layer, not the primary scoring input

Same role `crop_yield_observations` plays for agriculture: a real-station cross-check against
CAMS's modeled value, not the thing being scored. OpenAQ v3 confirmed live (real API key,
real stations returned for both event cities).

**Delhi coverage gap — a real, confirmed hole, not a shortcut:** every Delhi CPCB/DPCC PM2.5
sensor checked (5 stations: Delhi Technological University, IGI Airport, Civil Lines, R K Puram,
Punjabi Bagh — 2 sensors each where duplicated) has a coverage hole spanning exactly the Nov 2024
backtest window — data for each sensor either ends ~Feb 2018 or resumes ~Feb 2025, with nothing
in between. Not one station happens to gap this window; ALL of them do, consistently — most
likely a real provider/pipeline transition OpenAQ underwent for Indian CPCB stations. Reported as
a disclosed gap (same "absence isn't zero" honesty as seismic's `insufficient_data`); CPCB's own
published AQI=494 is the real anchor for Delhi, not an OpenAQ reading.

**California — full coverage, used successfully:** San Francisco AirNow station (OpenAQ sensor
3569, live 2016–present) covers the target window cleanly.

## 5. Backtest target 1: Delhi "severe plus" smog, 18 November 2024

CPCB AQI hit **494** ("Severe", 2nd-highest since 2015) as of 4pm on 18-Nov-2024; GRAP Stage IV
invoked 08:00 that day (construction halted, truck bans, schools closed citywide) [PIB press
release; The Wire]. Economic context: India-wide air pollution cost estimated at $95–260bn/year
(~3% of GDP); Delhi specifically ~6% of GDP/year.

**Result (`scripts/backtest_pollution.py`):** central Delhi scores **100.0 (VH)**, driver=pm25,
PM2.5=339.7µg/m³ (EAC4 reanalysis, daily mean of 4 six-hourly steps) — correctly severe, and the
raw concentration itself is consistent with widely-reported "hazardous" PM2.5 readings that day.
OpenAQ ground truth unavailable for this exact window (§4) — CPCB's AQI=494 is the cross-check.

## 6. Backtest target 2: California wildfire smoke, 10 September 2020 ("orange sky" peak day)

$11–20bn/yr short-term + $76–130bn/yr long-term PM2.5 health-cost estimates (peer-reviewed).
Cross-links to the EXISTING wildfire hazard — a real fire event driving both a wildfire score and
a pollution spike simultaneously, the same generalization-test role coffee played for cocoa's
heat mechanism.

**Result:** San Francisco scores **85.0 (VH)**, driver=pm25, PM2.5=56.2µg/m³ (EAC4 reanalysis)
vs. the real OpenAQ station reading of **129.0µg/m³** — ratio 0.44x, same order of magnitude,
model underestimates by more than half but correctly identifies the day as severe (bucket VH).
**Full week for context (real OpenAQ daily averages):** 11.7 → 27.2 → **129.5 (peak, 10 Sept)** →
150.9 → 93.7 µg/m³, 8–12 Sept 2020.

**Discrimination check:** the same day, a rural Swiss Alps reference point scores **10.5 (L)**,
PM2.5=7.8µg/m³ — correctly far below San Francisco's smoke-day reading, confirming the model
discriminates real severe pollution from clean air, not just returning a flat number.

## 7. Any-address on-demand path

`scripts/score_point_gridded_on_demand.py`'s `run_pollution_lookup` follows flood's exact
background-job shape (see `docs/` — the any-address lookup plan): fetch a small ad-hoc bbox
around the query point via `fetch_cams_forecast`, score every returned cell via
`pollution_score`, nearest-neighbor-fill the exact query cell when the CAMS grid (~40km) doesn't
naturally produce it (same H3-res8-vs-native-grid mismatch as flood's ERA5-Land), write
`canonical_scores` with `shap_factors` recording the driver pollutant, concentrations, and the
nearest-neighbor-fill flag. Verified end-to-end via the real API: `GET /v1/lookup/score` → 202
equivalent (`pending` + `lookup_id`) → poll → `done` with a real score, zero errors in the server
log (Bangkok: score 8.7, L).

## 8. Known limitations (stated up front)

- **PM2.5/PM10 only** — NO2/SO2/O3 deferred (§2), a real scope decision not silently assumed away.
- **CAMS's ~40km global grid underestimates acute, hyper-local wildfire smoke plumes** even using
  the correct reanalysis product (§6) — a real, disclosed model limitation, not a data bug; this
  is why the California backtest reports a 0.44x ratio rather than a clean match.
- **OpenAQ Delhi coverage gap** (§4) — no ground-truth cross-check available for the Nov-2024
  backtest window specifically; CPCB's own AQI figure substitutes.
- **Forecast-vs-reanalysis discipline must be maintained** — using the forecast archive for a
  past date silently underestimates severity (§3); any future pollution code must respect the
  `fetch_cams_forecast` (today only) vs `fetch_cams_reanalysis` (past dates) split.
- **CAMS forecast has a ~1-day publish lag** — `date.today()` is rejected; on-demand scoring uses
  `today - 1 day` (§3).

## 9. Files

- `ml/scoring/pollution_aqi.py` — WHO AQG breakpoints, per-pollutant sub-scores, max-of-sub-scores.
- `ml/features/pollution_cams.py` — `fetch_cams_forecast` / `fetch_cams_reanalysis` /
  `compute_features` (µg/m³, per-H3-cell).
- `scripts/score_point_gridded_on_demand.py` — `run_pollution_lookup`, the on-demand background job.
- `scripts/backtest_pollution.py` — the checks in §5/§6/discrimination check above.
- `core/config.py` — `ADSAPI_URL`/`ADSAPI_KEY` (confirmed to share CDS's personal access token
  post the 2024 ECMWF unification), `OPENAQ_API_KEY`.
- `core/db/migrations/versions/a2b3c4d5e6f7_pollution_hazard_vocab.py` — adds `pollution` to the
  `HazardType` CHECK constraints.
