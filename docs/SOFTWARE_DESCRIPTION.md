# Software Description Document — Tellumen Climate Risk Platform

## 0. Document control

| Field | Value |
|---|---|
| Document owner | Gaurav Sachdeva |
| Status | Living document — update on every material architecture change |
| Version | 1.0 |
| Last updated | 2026-07-04 |
| Package version (pyproject.toml) | 0.1.0 |

**Maintenance rule:** whenever a hazard type, service, data source, schema table, or auth
mechanism is added/changed/removed, update the relevant section below in the same PR/session as
the code change, and add one line to the [Change log](#12-change-log). Do not let this document
drift from the codebase — treat it as part of the deliverable, not an afterthought. Prefer marking
a section "TBD" over writing an unverified claim.

---

## 1. Executive summary

Tellumen is a multi-tenant climate-risk intelligence platform. It ingests satellite and
reanalysis data, scores physical climate hazards (volcanic, seismic, flood, wildfire, heat,
drought, storm, pollution) at H3-cell resolution, and exposes those scores to three customer
verticals — banking (asset exposure), insurance (parametric contracts, pricing), and agriculture
(supply-chain COGS-at-risk) — through an API, a web UI, and regulatory export packages
(CSRD/ECB/EIOPA/Taxonomy).

## 2. Scope

**In scope:** hazard ingestion and scoring, the operational loop (Sense → Score → Project → Act),
multi-tenant auth/RBAC, the three go-to-market verticals, regulatory reporting exports.

**Out of scope for this document:** day-to-day product roadmap detail (see root-level
`PHASE_*.md` / `IMPLEMENTATION_ROADMAP_PHASED.md`), per-hazard scientific methodology (see the
dedicated `docs/*_METHODOLOGY.md` files, linked in §11), brand/visual identity (`docs/BRAND.md`).

## 3. Architecture overview

| Module | Path | Purpose |
|---|---|---|
| API | `api/` | FastAPI REST service — auth (API keys + JWT), RBAC enforcement, scoring/data endpoints, admin console |
| Ingestion | `services/ingestion/` | Satellite/reanalysis adapters (NASA FIRMS, Copernicus Sentinel-1/3, ERA5, GloFAS, EMSC) and pipeline orchestration |
| Scoring | `ml/scoring/` | Physics-based (volcanic, seismic, storm) and ML-based (flood, wildfire, heat, drought, pollution) hazard scorers |
| Features | `ml/features/` | Feature engineering per hazard for the ML scorers |
| Intelligence | `services/intelligence/` | Vertical-specific logic — agriculture yield risk, supply-chain COGS, insurance pricing/loss curves, benchmarking |
| Regulatory | `services/regulatory_monitoring/` | CSRD/ECB/EIOPA/Taxonomy package generation, versioning, audit trail |
| Notifications | `services/notifications/` | Alerts, webhooks, email/SMS dispatch |
| Core | `core/` | DB models, session management, H3 geospatial utilities, config |
| UI | `ui/` | React/Vite frontend — risk map, ops dashboard, parametric contract view, compliance export |

Data flow: adapters (`services/ingestion`) → raw observations → hazard scorers (`ml/scoring`) →
append-only `canonical_scores` → consumed by `api/` for the UI, vertical intelligence modules, and
regulatory export.

## 4. Hazard catalog

| Hazard | Approach | Scorer | Primary data | Backtest anchor |
|---|---|---|---|---|
| Volcanic | Physics (distance-decay + curated zones) | `ml/scoring/volcanic_physics.py` | GVP eruption catalog + `volcanic_hazard_zones` | Fuego 2018, Taal 2020 |
| Seismic | Physics (IPE attenuation) | `ml/scoring/seismic_physics.py` | EMSC WFS, USGS | — |
| Storm | Physics (wind-decay) | `ml/scoring/storm_physics.py` | ERA5 wind, TC track data | — |
| Flood | ML (XGBoost ensemble) | `ml/scoring/engine.py` + `ml/features/flood.py` | Sentinel-1 SAR, ERA5 precip, GloFAS | 2021 Ahr Valley |
| Wildfire | ML | `ml/scoring/engine.py` + `ml/features/wildfire.py` | Sentinel-3 LST, ERA5, NASA FIRMS | 2022 Gironde |
| Heat | ML | `ml/scoring/engine.py` + `ml/features/heat.py` | ERA5, Sentinel-3 LST | 2003 European heatwave |
| Drought | ML | `ml/scoring/engine.py` + `ml/features/drought.py` | ERA5 precip, SPEI, GloFAS | — |
| Pollution | ML (WHO AQG-anchored) | `ml/scoring/pollution_aqi.py` | Copernicus CAMS | — |

Full scientific methodology and known limitations for each hazard live in the corresponding
`docs/*_METHODOLOGY.md`. **Note on FIRMS:** it feeds the wildfire scorer above; for volcanic it is
a supplementary monitoring signal only and is *not* an input to the volcanic score — see
`docs/VOLCANIC_HAZARD_METHODOLOGY.md` §2 for the full caveat.

## 5. Data architecture

Core tables (PostgreSQL + TimescaleDB + PostGIS):

- **Observations/ingestion:** `satellite_observations`, `seismic_events`, `flood_observations`,
  `wildfire_observations`, `heat_observations`
- **Scoring:** `canonical_scores` (append-only golden source: `h3_cell`, `hazard_type`,
  `risk_score`, `shap_factors`, `model_version`, `data_vintage`), `model_registry`
- **Financial/risk:** `parametric_contracts`, `contract_triggers`, `bank_assets`,
  `climate_hazard_exposure`, `damage_assessment`
- **Regulatory:** `regulatory_frameworks`, `regulation_versions`, `regulatory_package`,
  `sc_model_validation`
- **Asset-manager securities book:** `issuers`, `issuer_facilities`, `securities`, `funds`,
  `fund_positions`, `issuer_emissions`, `issuer_transition_scores` — the issuer/footprint/fund
  graph (distinct from the located-asset `portfolio_entities` model), keyed to the same golden
  source via `issuer_facilities.h3_cell → canonical_scores`.
- **Reference-data provenance:** every `issuers`/`securities`/`issuer_facilities`/`issuer_emissions`
  row carries `source` + `data_vintage` (+ `confidence` on facilities); `reference_resolution_log`
  records one row per ISIN resolution attempt (resolved/cached/unmatched/error) — the audit trail
  an SFDR filing cites.
- **Multi-tenancy:** `organizations`, `users`, `roles`, `permissions`, `api_keys`

`canonical_scores` is append-only; scores are never mutated in place, only superseded
(`valid_to`), which is what makes the backtest/audit trail reproducible.

**Reference-data resolution (open-data, no vendor license).** `services/reference/` turns a bare
ISIN — all an asset-manager client supplies — into an auditable issuer→security→footprint graph:
GLEIF (ISIN→LEI→issuer identity, free/keyless) resolves the issuer; the GLEIF headquarters address
is geocoded (Nominatim/OSM) and snapped to H3 res-8 to seed a footprint facility, scored via the
same any-address path (`services.scoring.on_demand`). Sector/NACE (absent from GLEIF) and
multi-facility footprints/emissions are surfaced as coverage gaps, never fabricated.

## 6. Security, multi-tenancy & access control

Tenancy model: `organizations` → `users` → `roles` → `permissions` (many-to-many). API auth uses
hashed API keys (`cp_live_<32hex>`, SHA-256 at rest, shown once at creation); session auth uses
JWT + bcrypt. Roles are org-scoped (admin, analyst, reporter, viewer); permissions are granular
(e.g. `admin.users.manage`, `data.scores.read`, `regulatory.export`). The admin console
(`api/routers/admin.py`) handles user/role/API-key lifecycle, with every mutation written to
`access_audit_log`. Enforcement is centralized in `api/services/rbac.py` and
`api/deps.py::require_permission()`.

## 7. Deployment & infrastructure

- `infra/docker/Dockerfile` — multi-stage build: `api-deps` (FastAPI + XGBoost/LightGBM/MLflow),
  `ingest-deps` (GDAL/HDF5/NetCDF/rasterio); produces an API image (Uvicorn, `:8000`, health
  check) and a worker image (per-hazard-type scoring process).
- `docker-compose.yml` — local dev stack: PostgreSQL 16 + TimescaleDB (`:5433`), MLflow (`:5001`,
  SQLite backend), Adminer (`:8080`).
- Database requires PostGIS and `uuid-ossp` extensions in addition to TimescaleDB.

## 8. External interfaces

REST API (`api/`) is the sole external interface: scoring/data endpoints, admin/user management,
regulatory export. No other externally-facing services currently exist. Data adapters
(`services/ingestion/adapters/`) are the platform's only outbound integrations: NASA FIRMS,
Copernicus Sentinel-1/3, ERA5, GloFAS, EMSC. The reference-data layer (`services/reference/`) adds
two further outbound open-data integrations: GLEIF (LEI/ISIN resolution) and Nominatim/OSM
(headquarters geocoding).

## 9. Non-functional characteristics

TBD — no verified SLAs, throughput, or scaling benchmarks exist yet. Do not populate this section
with estimates; fill in once real numbers (load tests, prod metrics) exist.

## 10. Known limitations (platform-level)

- No centralized `CHANGELOG.md`/`VERSION` file — versioning today is implicit via git history,
  `model_registry.model_version`, and `regulation_versions.version_number`. This document's own
  §12 change log is the first step toward closing that gap for architecture-level changes; a
  code-level CHANGELOG is a separate, not-yet-scheduled task.
- Per-hazard scientific limitations are documented individually in each
  `docs/*_METHODOLOGY.md` — this document intentionally does not restate them.

## 11. Related documents

- `docs/VOCABULARY.md` — canonical hazard/scenario/risk-bucket terms
- `docs/MULTI_SECTOR.md` — banking/insurance/agriculture architecture
- `docs/*_METHODOLOGY.md` — one per hazard type (volcanic, seismic, storm, pollution, supply-chain)
- `docs/BACKTEST_DATA.md` — backtest event dataset status
- `docs/investor_brief.md`, `docs/objection_tracker.md` — external/market-facing material

## 12. Change log

| Date | Version | Change |
|---|---|---|
| 2026-07-04 | 1.0 | Initial Software Description Document created. |
| 2026-07-11 | 1.1 | Added asset-manager securities book + reference-data resolution layer (open-data ISIN→issuer→footprint via GLEIF + Nominatim, with provenance and an ISIN-resolution audit log). |
