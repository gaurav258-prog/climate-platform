# Tellumen — Golden Data Sources (global coverage of record)

The physical-risk engine scores **any H3 res-8 cell on Earth on demand** from a set of *global* golden
sources. It is not a pre-computed dense grid (that would be billions of rows at res-8); it scores a cell
when an asset or address touches it, reading a **global baseline** for the continuous-field hazards and a
**global catalog** for the event/proximity hazards. This doc is the source of record: for each layer, the
authoritative global source, its native resolution, cadence, and the *state of our ingestion path*.

Positioning: every source below is a **direct authoritative feed from Europe's & America's satellites and
agencies** (Copernicus/ECMWF, NASA, USGS, NOAA, Smithsonian). We never describe them as "free/open/cheap."

## Coverage model — two kinds of hazard

- **Continuous fields** (drought, heat, soil-water, frost, flood, wildfire, pollution): a value exists
  everywhere on land. We score them from a **global climatological baseline** + a live reading, so the
  score is defined at any cell. Global-ready ⇔ the *baseline* is global.
- **Event / proximity hazards** (seismic, storm, volcanic): risk concentrates near faults / cyclone tracks
  / volcanoes. We score them from a **global event catalog** and physics, so a cell far from any source is
  correctly low/none — global-ready ⇔ the *catalog* is global.

## Hazard sources

| Hazard | Authoritative source | Agency | Native res | Cadence | Coverage of record |
|---|---|---|---|---|---|
| Drought (SPEI) | ERA5 monthly means (t2m, total precip) → `climatology_baseline` | Copernicus / ECMWF | 0.25° | monthly | **Global** (baseline built, −90..90) |
| Heat — acute & chronic | ERA5 t2m climatology → `climatology_baseline` | Copernicus / ECMWF | 0.25° | monthly | **Global** (same baseline) |
| Soil-water stress | ERA5 monthly volumetric soil water L2+L3 → `soil_moisture_baseline` | Copernicus / ECMWF | 0.25° | monthly | **Global** (baseline build G1) |
| Frost | ERA5 **daily-minimum** 2m temperature → `frost_baseline` | Copernicus / ECMWF | 0.25° | daily→clim | **Global** (daily-min baseline, build G2) |
| Flood | ERA5-Land total runoff (proxy) | Copernicus / ECMWF | 0.1° | daily | **Global** (GloFAS withdrawn from CDS 2025; runoff proxy, DEM/river-gauge terrain not yet landed) |
| Wildfire | NASA FIRMS (VIIRS active fire) | NASA | 375 m | daily | **Global** (Sentinel-3 SLSTR LST integration stubbed) |
| Storm / cyclone | NOAA IBTrACS tracks + Modified-Rankine-Vortex physics → `storm_events` | NOAA | per-track | daily | **Global** (all 6 basins; 966 storms / 35,846 track points, last 10y) |
| Seismic | **USGS** global earthquake catalog M≥5.0 → `seismic_events` + physics point-scorer | USGS | epicentral | on ingest | **Global** (17,939 events, −70..87 lat, −180..180 lon). ESHM20/EMSC is a *secondary EU background raster*, not the scoring path. |
| Volcanic | Smithsonian GVP eruptions + curated per-volcano hazard zones | Smithsonian | per-volcano | daily | **Regional/curated** — hazard zones hand-curated per volcano; no generic global fallback formula yet (documented gap) |
| Pollution / air quality | Copernicus CAMS (fetched per-query) | Copernicus | 0.4° | daily | **Global on-demand** (out of the CSRD/EUDR filing scope; informs the risk view) |

## Reference / non-hazard sources

| Layer | Source | Agency | Coverage | State |
|---|---|---|---|---|
| Legal entity (ISIN→LEI→issuer) | GLEIF | GLEIF | **Global** | live |
| Deforestation (EUDR) | Hansen Global Forest Change | UMD / Google | **Global** | on-demand at determination time |
| Emissions estimate | NACE sector-intensity × revenue | — | Global | **estimated** (not a Climate TRACE/GEM facility feed — labelled estimated throughout) |
| FX | ECB reference rates → `fx_rates` | ECB | Global currencies | live |
| Crop prices | World Bank "Pink Sheet" | World Bank | Global commodities | live |

## What is genuinely NOT global yet (honest gaps)

1. **Volcanic** — hazard zones are curated per volcano; a global proximal/ashfall fallback formula is not
   decided. Out of the climate-regulatory scope, so it does not affect a CSRD/EUDR filing.
2. **Flood** is a runoff *proxy* (GloFAS withdrawn from the CDS in 2025). The observed-flood upgrade —
   **Sentinel-1 SAR** VV backscatter — is now code-complete: the adapter computes per-H3-cell terrain-
   corrected gamma0 (dB) server-side via the **CDSE Sentinel Hub Statistical API** (no SNAP, no scene
   downloads), lands `sar_backscatter_db` + a 7-day anomaly into the flood ML feature set, and flags
   open-water inundation (VV ≤ −17 dB). It **activates on a free CDSE Sentinel Hub credential**
   (`SENTINEL_HUB_CLIENT_ID`/`SECRET`); until then the feed stays `planned` (stub-only for dev) — nothing
   is landed and the registry says so.
3. **Wildfire** LST enrichment (Sentinel-3 SLSTR), **Sentinel-2 NDVI**, and **storm** sea-state (Copernicus
   Marine) are stubbed secondary layers; the primary catalogs (FIRMS, IBTrACS) are global and live.

## The €-at-risk layer is scoped on purpose (not a coverage gap)

The **hazard scores** above are global. The agriculture **€ COGS-at-risk** figures are published only for
crop×origins we have **backtested** (the r²≥0.40 honesty gate) — a deliberate scope, not a data limit. The
hazard layer under an un-validated crop is still global; we simply withhold the euro until the
hazard→yield chain is validated for that crop×origin. See `docs/CALC_ENGINE_AUDIT.md`.

## Baselines of record (global)

| Table | Variable | Source product | Rows | Extent |
|---|---|---|---|---|
| `climatology_baseline` | t2m mean/std, precip mean/std (per cell/month) | ERA5 single-levels monthly-means | ~12.3M | Global (−90..90) |
| `soil_moisture_baseline` | root-zone volumetric water mean/std | ERA5 monthly swvl2+swvl3 | build G1 | Global |
| `frost_baseline` | climatological coldest-night min-temp | ERA5 daily-min t2m | build G2 | Global |

_Last updated: 2026-08-01 (global build). Update this doc whenever a source, its coverage, or a maturity
state changes — it is the disclosure of record behind the feed registry (`services/data/feeds.py`)._
