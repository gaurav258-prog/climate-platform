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
| 2026-07-19 | 1.24 | **Projections upgrade — regional warming amplification (AR6-grounded, parametric v1) + two more grade-A rain-fed crops.** (1) The scenario deltas (`SCENARIO_WARMING_C`) are GLOBAL-MEAN warming, but assets sit on LAND, which warms faster than the mean and more so toward the poles. `ml/scoring/heat_climatology.py` now centralises the shift in `warming_delta(scenario, horizon, lat)` = global delta × `warming_amplification(lat)` where `amp(lat)=LAND_BASE(1.40)+POLAR_K(1.5)·(|lat|/90)²`, capped 3.0 — reproducing AR6 zonal LAND ratios (equator ~1.40, Mediterranean 37° ~1.65, N-Europe 52° ~1.85, sub-Arctic 65° ~2.18). All five climatology scorers (heat/drought/soil_water/frost/heat_chronic) take an optional `lat` and route through it; the point-scorers and crop/cocoa belt-scorers thread the cell latitude. **The current horizon is 0 warming, so amplification NEVER touches a live score — only 2030/2050/2100 projections** (score-lane invariant preserved; re-scored belts retire only their own standing forward scores). Effect on the flagship: Spain olive hot-house-2100 band widens €0–7.4m → **€0–9.3m** (Mediterranean warms ~1.65× global); tropical cocoa barely moves (lat ~6 → ~1.44×, physically correct); Terra book current €4.65m UNCHANGED, hot-house-2100 total €10.4m → €13.3m. This is a PARAMETRIC shift of today's climatology, honest about land+latitude — NOT downscaled CMIP6 (still the tracked next step); it does not add the Mediterranean summer DRYING hotspot beyond temperature. `tests/unit/test_warming_amplification.py` pins the invariants (monotone in lat, symmetric, capped, current-horizon never amplified). (2) Fitted **Algeria + Tunisia wheat** (Maghreb rain-fed durum, drought SPEI-6 Jan–Jun water year, same rule as olive): **Tunisia r²=0.636 in / 0.575 out → Confidence Grade A** (2nd grade-A crop), **Algeria r²=0.565 / 0.479 → grade C**; Morocco stays A. Foundational fix: `sc_commodity_calibration.world_share` was stale-NOT NULL (blocked the fit INSERT path for a new origin with no curated share) → migration `world_share_nullable_20260719` drops it (read-path already sums only non-NULL shares). (3) The Models & validation credibility record now shows origins as readable country names (`originName` in the UI vocabulary; "Wheat · Morocco", not "Wheat MA"). Suite 294 passed. |
| 2026-07-19 | 1.23 | **Water-availability layer + Confidence Grade + rain-fed proof + the honest reservoir null-result.** (1) **Root-zone soil water** as a DISTINCT hazard `soil_water` (ERA5-Land layers 2+3, depth-weighted; `ml/features/soil_moisture.py`, `ml/scoring/soil_water_climatology.py`; added to `core.types` + hazard-vocab migration). Tested head-to-head vs SPEI per crop (`scripts/compare_water_drivers.py`): olive tie, wine SPEI wins, **dryland wheat soil-moisture WINS (0.36→0.445)** — so Spanish durum wheat now PUBLISHES ranged (r²=0.42, band, driver=soil_water). A cell carries BOTH hazards; a calibrated crop displays its own driver. (2) **Rain-fed origins prove the thesis**: ingested wheat yield for 7 rain-fed origins (MA/DZ/TN/AU/TR/SY/AR, 64yr FAOSTAT); **Morocco wheat = first grade-A crop** — drought SPEI-3 Jan–Apr, in-sample r²=0.673, **out-of-sample 0.629**, because a genuinely rain-fed crop is not decoupled from climate by irrigation. (3) **Confidence Grade A–E** (`ml/confidence_grade.py`): transparent 4-check composite (out-of-sample LOO-CV r² + evidence depth + band calibration + proof type), honesty cap (weak predictive → max C), sits ON TOP of the visible stats (deliberately NOT a rename of r²); shown via `ui/src/components/GradeBadge.jsx` on CogsCommand + SupplyModels. `crop_fit.py` now emits `r2_oos` + `band_cov68`; migration `fit_validation_stats_20260718`. (4) **Reservoir/irrigation water — tested, does NOT clear the bar, crops stay held (honest null-result).** Distilled the MITECO Boletín Hidrológico MDB (weekly storage 1988–2026, every Spanish reservoir >5hm³) into a compact per-basin monthly fill index (`scripts/build_reservoir_index.py` → `data/reservoirs/basin_reservoir_index.csv`; raw 213MB MDB gitignored). Regressed decomposed yield on basin fill (`scripts/compare_reservoir_driver.py`): beet/Duero r²=0.02 (wrong sign), citrus/Júcar+Segura r²=0.07 (right sign, LOO-negative), almonds r²≈0.00. **Interpretation: irrigation is a buffer — when it works it DECOUPLES yield from water availability, so basin storage only bites in rare hard-restriction years and can't reach r²=0.40 on ~18–34 noisy national points**; beet is further confounded by the 2006 EU sugar-quota area collapse (a policy signal). No number faked; these crops remain held. The reservoir index + harness are kept as durable assets for future restriction-year / projection work. |
| 2026-07-18 | 1.22 | **Agriculture crop calibration — the 'ranged' tier + honest cyclical-crop validation.** Three-tier calibration derived (never typed) in `v_sc_commodity_calibration`: **indicative** (v0 defaults, € withheld) → **ranged** (a driver explains the crop PARTLY; € published as a BAND with r² stated) → **backtested** (reproduces a real event; € as a point). `sc_commodity_fit` stores the multi-year OLS (slope/intercept/r²/rmse + n/score_mean/score_sxx for a real prediction interval); `ml/features/crop_fit.py` fits, `scripts/fit_ranged_crop.py` persists (MIN_R2=0.40). The engine (`services/intelligence/supply_cogs.py`) emits `volume_at_risk_low/high_eur` + `fit_r2` for a ranged origin, floored at 0 (a favourable year is a gain, not "volume at risk"); the publish gate lets 'ranged' through. **Cyclical-crop validation target** (`ml/features/world_shock.py`): a crop that alternate-bears (olive/wine/almonds) must NOT be validated against FAO's raw world shock — it bundles the tree cycle and nets damage against other origins' good years. Decomposed into raw / net / **damage** (losses only), the damage figure is the target a damage-only model can reproduce. Ingested 13 material FAOSTAT origins (Türkiye/Morocco/Syria/etc.; China=41 mainland not the 351 aggregate) lifting olive world coverage 66%→97%. **Reference crop: Spain olive**, drought SPEI-6 (the agronomic water-year window, r²=0.51 over 31 yrs; heat adds nothing), scored onto the belt (`scripts/score_crop_drought.py` (parametric: region+commodity), standing lane, scenario×horizon) → olive flips from "€ pending" to a live range that rises under warming (baseline €0–€4.1m → hot-house-2100 €0–€7.4m). **USP finding**: tested and DISPROVED that finer spatial resolution tightens the fit (r² 0.51 belt vs 0.47 Jaén) — the ceiling is national crop-data noise, not hazard resolution; so the pitch is footprint-breadth + filing-integration + auditability + honest-uncertainty (the band is a trust asset) + live/early, NOT point-accuracy. `measured_basis` disclosed per crop (olive = the fruit, not oil). Retired the dead price-amplification chain from the published path. Suite 278 passed. |
| 2026-07-13 | 1.21 | Enterprise completeness sweep (8 gaps closed to widen the beachhead). **FX** — a non-EUR line (market_value + currency) converts to EUR at the ECB reference rate on-or-before the book's as-of date; fx_rates table (seeded ECB 2023-12-29, scripts/load_fx_rates.py pulls live), fund_positions stores native value+currency; unknown currency is a surfaced error, never assumed. **Taxonomy DNSH gate** — issuer_esg_metrics gains dnsh_ok/min_safeguards_ok; an explicit FALSE excludes that issuer's reported aligned% (surfaced as aligned_excluded_dnsh_pct); NULL preserves prior behaviour. **Voluntary PAI** — ml/regulatory/voluntary_pai.py catalog of real RTS Table 2/3 indicators; per-fund selection (fund_voluntary_pai) + per-issuer values (issuer_voluntary_pai); computed roll-up (weighted-avg / share-of-value) replaces the declaration stub; GET /voluntary-pai/catalog, PUT /funds/{id}/voluntary-pai. **Entity-level roll-up** — entity_pai_statement value-weights every position across ALL a manager's funds (scope override on fund_pai/fund_esg_pai/_taxonomy_rollup/_composition/voluntary; shared _mandatory_indicator_rows); GET /entity/sfdr-statement + per-fund coverage table. **Batch orchestration** — sfdr_batch_runs/items + services/sfdr_batch.py generate statements across the whole book, resumable (chunked via limit, one bad fund can't abort); POST /entity/sfdr-batch(/{id}/run), GET /entity/sfdr-batch/{id}. **Vendor connector** — services/reference/vendor_ingest.py maps MSCI/ISS (or custom) extracts, matches by ISIN/LEI, stores source='vendor'; read-path precedence own>vendor>global (tiebreaker added to the emission/ESG/taxonomy LATERALs); POST /vendor/ingest, GET /vendor/profiles. **XBRL** — ml/regulatory/sfdr_xbrl.py emits a valid XBRL instance (contexts=manager LEI+period, units, tagged facts, PAI1 split by scope); GET /funds/{id}/sfdr-statement.xbrl + /entity/sfdr-statement.xbrl (Tellumen placeholder taxonomy, swap for ESMA's). **UI** — header-aware holdings paste exposes every intake column (currency, EVIC, ESG 5-14, Taxonomy+DNSH); XBRL download on the statement page. Also fixed 2 pre-existing test failures (frost hazard alias; packages error-envelope assertion). Full suite 218 passed. |
| 2026-07-04 | 1.0 | Initial Software Description Document created. |
| 2026-07-11 | 1.1 | Added asset-manager securities book + reference-data resolution layer (open-data ISIN→issuer→footprint via GLEIF + Nominatim, with provenance and an ISIN-resolution audit log). |
| 2026-07-11 | 1.2 | Added SFDR PAI statement (the filing): ml/regulatory/sfdr_pai.py assembles the mandated RTS Annex I Table 1 (14 investee indicators — computed where honest, gap-flagged with the exact input otherwise) + EU Taxonomy lines; JSON + downloadable .xlsx endpoints; asset-mgmt SFDR filing UI. Common EU-listed universe pre-loaded via scripts/load_reference_universe.py. |
| 2026-07-12 | 1.3 | Client issuer-data enrichment: onboarding accepts optional NACE/revenue/scope1-3 per holding to fill more of the SFDR statement. Emissions are org-scoped private disclosures (issuer_emissions.org_id; global org_id NULL = estimated/public fallback), source='client'; NACE stays a global fact (enrich-if-unknown). fund_disclosure prefers the org's own disclosure over the global fallback. |
| 2026-07-12 | 1.4 | Emissions estimation gap-fill: services/reference/emissions_estimation.py estimates scope 1+2 = NACE sector-average intensity × revenue when no scope is disclosed (source='estimated', method disclosed; scope 3 not estimated). Wired into onboarding. SFDR statement now discloses the reported-vs-estimated split (emissions_estimated_pct) per RTS. Intensity coefficients are illustrative sector averages pending an EXIOBASE-sourced table (flagged in code). |
| 2026-07-12 | 1.5 | Sovereign & real-estate PAI tables (RTS Annex I indicators 15–18). Sovereign 15 (GHG intensity of investee countries) computes from a public country-intensity table when the fund holds sovereign bonds; 16 (social violations) gap-flagged. Real-estate 17–18 shown as not-applicable for securities funds (applies to direct property). SFDR statement JSON/xlsx/UI gain sovereign_indicators, real_estate_indicators, holdings_composition. |
| 2026-07-12 | 1.6 | Universe pre-load scaling: geocoder is now config-driven (NOMINATIM_URL + NOMINATIM_MIN_INTERVAL_S) so a self-hosted Nominatim drops in without code changes; rate limiter is thread-safe; loader gains --workers for parallel resolve+locate (safe default 1 against public Nominatim's 1 req/s policy, raise only with a permissive/self-hosted geocoder). The remaining scale limit is deployment (run a self-hosted geocoder), not code. |
| 2026-07-12 | 1.7 | Financed emissions PAI 1/2 via EVIC. Migration c2d3e4f5a6b7 adds issuer_emissions.evic_eur. Onboarding accepts evic_eur per holding; fund_pai computes PCAF financed emissions (attribution = market value ÷ EVIC) and PAI 2 carbon footprint (financed ÷ €M invested), with financed_emissions_coverage_pct disclosed and computed/partial by coverage. SFDR statement/UI/xlsx show PAI 1 as financed. Fixed: enrichment ON CONFLICT now COALESCEs so a partial follow-up (e.g. EVIC only) fills gaps without erasing earlier figures. |
| 2026-07-12 | 1.20 | Article 8/9 periodic report (SFDR RTS Annex IV/V). ml/regulatory/sfdr_periodic.py assembles the periodic disclosure: product characteristics, E/S attainment (sustainability indicators computed, narrative flagged), EU-Taxonomy alignment (from the alignment roll-up), asset allocation + sustainable-investment share (need the manager's per-holding classification — flagged), PAI-considered, and top investments. GET /v1/funds/{id}/periodic-report; new "Periodic report" UI page + nav. Article-8/9 only. |
| 2026-07-12 | 1.19 | Look-through expansion. POST /v1/funds/{id}/look-through takes a held fund/ETF's constituents, creates a sub-fund (parent_fund_id) holding them (values scaled to preserve the wrapper's exposure), and removes the wrapper position — so the underlying issuers flow into the fund's PAI via the existing descendant roll-up, with no double-count. look_through status reports applicable/expanded honestly. |
| 2026-07-12 | 1.18 | EU Taxonomy alignment. Migration taxonomy_align_20260712 adds issuer_esg_metrics.taxonomy_eligible_pct / taxonomy_aligned_pct — the issuer's own Article-8 reported figures (org-scoped disclosure, supplied on onboarding). _taxonomy_rollup value-weights the reported aligned/eligible % over the whole book, discloses alignment_coverage_pct, and asserts alignment ONLY from reported issuer data (never infers DNSH/minimum-safeguards). UI taxonomy cards show real aligned/eligible % + reported-coverage. /health fixed (duplicate handler removed; real text()-wrapped DB probe). |
| 2026-07-12 | 1.17 | Correctness/honesty audit fixes (fresh-eyes review of the SFDR module). (1) EVIC attribution factor capped at 1.0 and EVIC/revenue required strictly positive (Holding gt=0, scopes ge=0) — a tiny/mis-keyed/negative EVIC no longer inflates or inverts financed emissions PAI 1/2. (2) Year-on-year change only computed when prior & current indicator share the same method — an un-attributed→financed PAI 1 no longer fabricates a ~99% move (shows prior value + a "not comparable" note instead). (3) Umbrella funds: reference-year, taxonomy and composition/sovereign now roll up fund descendants (were parent-only). (4) Reference-year detection org-scoped + counts distinct issuers (was raw rows across tenants). (5) Cross-tenant leak fixed: issuer_detail emissions read now org-scoped. (6) Negative revenue excluded from WACI. (7) Duplicate ISIN lots aggregated, not dropped (weights were understated). (8) PAI 4 fossil coverage now reflects known-NACE share (was hard-coded 100%). Regression tests added for the EVIC cap and YoY method-mismatch. |
| 2026-07-12 | 1.16 | Remaining filing pieces. (1) PCAF data-quality score (1 best–5 worst), value-weighted from the emissions source per holding, in fund_pai + statement + UI. (2) Additional (voluntary) PAI declaration block (RTS Tables 2&3 — manager must adopt ≥1 climate + ≥1 social; surfaced as declaration_required). (3) Look-through detection from asset_class (held funds/ETFs flagged for constituent expansion; n/a for direct securities). (4) Mandatory narrative sections (migration narratives_20260712 → organizations.sfdr_narratives JSONB): policies / actions / engagement / standards; set via /manager/filing-profile; now gate filing readiness; UI narrative form + xlsx summary rows. |
| 2026-07-12 | 1.15 | Prior-year comparison (SFDR year-2 requirement). Migration sfdr_filings_20260712 adds fund_sfdr_filings — an immutable frozen statement snapshot per fund per reference year (mirrors bank_disclosure_submissions). POST /v1/funds/{id}/sfdr-statement/file freezes the current statement; GET /sfdr-filings lists history. sfdr_pai looks up the most recent prior filing and attaches each indicator's prior_value + change/change_pct + a comparison block. UI: "File statement" button (enabled once ready to file), a "vs FY<prior>" badge, and per-indicator ▲/▼ change vs prior. Two-period demo (files FY2022, shows FY2023 YoY). |
| 2026-07-12 | 1.14 | Filing identity + readiness. Migration filing_identity_20260712 adds LEI/legal_name/filing_contact_email to organizations (the FMP) and lei to funds. PUT /v1/manager/filing-profile validates the manager LEI against GLEIF (real, active) and auto-pulls the legal name; PUT /v1/funds/{id}/lei for the fund LEI. The SFDR statement gains a filing_readiness block (ready_to_file + missing entity fields); UI shows a green "Ready to file" or an amber inline LEI/contact form that flips it. This is the gate between a computed statement and a submittable one. |
| 2026-07-12 | 1.13 | Non-carbon PAI indicators (5-14) made fillable. New issuer_esg_metrics table (org-scoped, migration esg_metrics_20260712) holds energy mix/intensity, biodiversity, water, hazardous waste, UNGC/OECD violation + monitoring flags, gender pay gap, board diversity, controversial weapons. Onboarding accepts them; services.fund_disclosure.fund_esg_pai computes PAI 5-14 (value-weighted ratios, exposure shares for flags, EVIC-attributed absolutes for water/waste); sfdr_pai fills those rows with coverage. A fully-documented book now computes all 14 mandatory indicators — 0 left "awaiting input". |
| 2026-07-12 | 1.12 | EXIOBASE calibration RUN. scripts/build_nace_intensities.py now computes real NACE sector GHG intensities from EXIOBASE 3 (IOT_2022_ixi, impacts/S GWP100 ÷ output, EU-region output-weighted), pulling only the two needed matrices (~23 MB) from the 755 MB archive via HTTP range requests (remotezip). data/reference/nace_emission_intensity.csv now holds EXIOBASE values for the 53 divisions EXIOBASE distinguishes (e.g. electricity 1247, air transport 735, software 14, banking 16.5 tCO2e/€M); the estimator merges these over the embedded interim table so the ~32 divisions EXIOBASE folds (e.g. pharma) keep coverage. MODEL_VERSION → emissions-est-v2-exiobase. Tests assert the EXIOBASE values load and pass sanity ranking. |
| 2026-07-12 | 1.11 | Coefficient calibration & externalisation. Intensity coefficients moved out of code into provenanced data files: data/reference/country_ghg_intensity.csv (REAL values computed from OWID / Global Carbon Project CO2 ÷ GDP, 2022, via scripts/build_country_intensities.py) and data/reference/nace_emission_intensity.csv (interim sector averages, source-flagged; scripts/build_nace_intensities.py documents the EXIOBASE 3 calibration pipeline). emissions_estimation + sfdr_pai load the CSVs at runtime (embedded fallback offline). Statement provenance cites the actual sources/vintages. Tests: intensities load from the data files and sovereign values are the real OWID-derived figures. |
| 2026-07-12 | 1.10 | Data-quality hardening: tests around the make-or-break math — emissions estimation (intensity×revenue, safe degradation, no scope-3 estimate), reference-resolution guard clauses (malformed ISIN/LEI rejected before any network call), PAI indicator structure (all 14 present, real-estate not-applicable, sovereign computes/gaps), and exact-arithmetic PCAF integration tests (financed emissions, WACI, carbon footprint; partial-without-EVIC). Estimation/country intensity coefficients remain flagged in-code as illustrative pending EXIOBASE calibration before a production filing. |
| 2026-07-12 | 1.9 | Design-partner self-serve: GET /v1/holdings/template.csv returns a documented holdings template (required isin+value; optional NACE/revenue/scope1-3/EVIC/asset_class/reporting_year) a manager fills with their own book; onboarding UI gains a "Download template" link. Trial path is the existing demo login. |
| 2026-07-12 | 1.8 | Filing-grade output. sfdr_pai_statement gains an RTS declaration summary (manager/LEI, reference period from emissions vintage, prior-period N/A, PAI-considered) and a provenance appendix (data sources + vintages, model versions, reported/estimated/financed coverage, methodology notes). Downloadable .xlsx is now a 3-sheet workbook — Summary, PAI statement (RTS Table 1 columns: Indicator/Metric/Impact[ref]/Impact[prior]/Explanation/Actions, grouped investee/sovereign/real-estate), Provenance & methodology — with fit-to-width print setup. Manager LEI surfaced as a required input (organizations has no LEI column yet). UI shows reference period + LEI-required + download contents. |
