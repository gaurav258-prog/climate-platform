# Technical requirements — Tellumen climate platform (as built)

> **Generated — do not edit by hand.** Written by `scripts/build_project_docs.py` from `pyproject.toml`, `web/package.json` and its lock file, `.github/workflows/ci.yml`, `scripts/precommit.sh`, `infra/`, `docker-compose.yml`, `core/config.py`, the API's OpenAPI schema and the Celery beat schedule. Regenerate with `venv/bin/python -m scripts.build_project_docs --write`; the gate (`scripts/precommit.sh`) fails when this file differs from what the code produces now.

What the platform runs on and how it is built, tested and deployed. The architecture, data, security, deployment and interface prose is in [SOFTWARE_DESCRIPTION.md](SOFTWARE_DESCRIPTION.md) §3 and §5–§9 and is linked here, not repeated. The database schema is [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md); the screens and routes are [APP_FLOW.md](APP_FLOW.md).

## 1. Runtime

| Component | Version | Where it is stated |
|---|---|---|
| Package | `climate-platform` 0.1.0 | `pyproject.toml` [project] |
| Python | `>=3.14,<3.15` | `pyproject.toml` requires-python |
| Python (CI) | `3.14` | `.github/workflows/ci.yml` env.PYTHON_VERSION |
| Python (container) | `python:3.14-slim` | `infra/docker/Dockerfile` first stage |
| Node.js (CI) | `25` | `.github/workflows/ci.yml` job web |
| TypeScript | `~6.0.2` → 6.0.3 | `web/package.json` / lock file |
| PostgreSQL (CI) | `timescale/timescaledb:latest-pg16` | `.github/workflows/ci.yml` integration-tests service |
| PostgreSQL (local stack) | `timescale/timescaledb:latest-pg16` | `docker-compose.yml` service db |
| Database migrations | 309 revisions, head `loss_msg_20261017` | `core/db/migrations/versions/` |

## 2. Backend dependencies (Python)

Declared in `pyproject.toml` — the one dependency list (`tests/unit/test_environment_matches_requirements.py` checks the environment against it). `core` is installed always; the others are extras (`pip install -e ".[all,dev]"` in CI). *Note* is the comment beside or above the line in the file.

### `core`

| Requirement | Note |
|---|---|
| `sqlalchemy>=2.0` | Database |
| `alembic>=1.13` | Database |
| `psycopg[binary]>=3.1` | psycopg3 — matches requirements.txt + .env (postgresql+psycopg://) |
| `numpy>=1.26` | Core numerics |
| `pandas>=2.2` | Core numerics |
| `h3>=4.0` | H3 geospatial indexing |
| `shapely>=2.0` | Plot geometry — EUDR polygon boundaries: GeoJSON parse + geodesic area (no PostGIS) |
| `pyproj>=3.6` | Plot geometry — EUDR polygon boundaries: GeoJSON parse + geodesic area (no PostGIS) |
| `python-dotenv>=1.0` | Config |
| `pydantic-settings>=2.2` | Config |

### `api`

| Requirement | Note |
|---|---|
| `fastapi>=0.110` |  |
| `uvicorn[standard]>=0.27` |  |
| `httpx>=0.27` |  |
| `xgboost>=2.0` | ML inference only (scoring engine) |
| `lightgbm>=4.0` | ML inference only (scoring engine) |
| `scikit-learn>=1.4` | ML inference only (scoring engine) |
| `mlflow>=2.11` | ML inference only (scoring engine) |
| `bcrypt>=4.1` | Auth — user login (bcrypt) + JWT session tokens |
| `PyJWT>=2.8` | Auth — user login (bcrypt) + JWT session tokens |
| `signxml>=5.0` | Enterprise SSO + MFA — SAML XML-DSig (signxml/lxml), WebAuthn passkeys, TOTP-enrolment QR |
| `lxml>=5.0` | Enterprise SSO + MFA — SAML XML-DSig (signxml/lxml), WebAuthn passkeys, TOTP-enrolment QR |
| `webauthn>=2.0` | Enterprise SSO + MFA — SAML XML-DSig (signxml/lxml), WebAuthn passkeys, TOTP-enrolment QR |
| `qrcode>=8.0` | Enterprise SSO + MFA — SAML XML-DSig (signxml/lxml), WebAuthn passkeys, TOTP-enrolment QR |
| `openpyxl>=3.1` | Excel upload parsing (loan tapes / SOV / filing workbooks) + validated uploads |
| `reportlab>=4.0` | Excel upload parsing (loan tapes / SOV / filing workbooks) + validated uploads |
| `python-multipart>=0.0.9` | Multipart form parsing — required by FastAPI for the file-upload endpoints |
| `requests>=2.31` | CRCS: the EU register (Cellar SPARQL) and regulators' RSS feeds — HTTP only, no page scraping |
| `prometheus-client>=0.20` | Observability — /metrics (security headers do not depend on it; see api/security_headers.py) |
| `pdfplumber>=0.11` | Prior-filings PDF parsing (decompose past filings to template cells) |
| `celery>=5.3` | Background workers — Celery task queue + Redis broker/result backend |
| `redis>=5.0` | Background workers — Celery task queue + Redis broker/result backend |

### `ingest`

| Requirement | Note |
|---|---|
| `rasterio>=1.3` |  |
| `xarray>=2024.1` |  |
| `pyproj>=3.6` | Plot geometry — EUDR polygon boundaries: GeoJSON parse + geodesic area (no PostGIS) |
| `cdsapi>=0.7` |  |
| `netCDF4>=1.6` |  |
| `httpx>=0.27` |  |
| `gcsfs>=2024.2` | raw CMIP6 delta-change projections (Pangeo zarr archive on Google Cloud) |
| `zarr>=2.17` | raw CMIP6 delta-change projections (Pangeo zarr archive on Google Cloud) |
| `fsspec>=2024.2` | raw CMIP6 delta-change projections (Pangeo zarr archive on Google Cloud) |

### `train`

| Requirement | Note |
|---|---|
| `xgboost>=2.0` | ML inference only (scoring engine) |
| `lightgbm>=4.0` | ML inference only (scoring engine) |
| `shap>=0.44` |  |
| `scikit-learn>=1.4` | ML inference only (scoring engine) |
| `mlflow>=2.11` | ML inference only (scoring engine) |

### `otel`

| Requirement | Note |
|---|---|
| `opentelemetry-sdk>=1.41` |  |
| `opentelemetry-exporter-otlp-proto-http>=1.41` |  |
| `opentelemetry-instrumentation-fastapi>=0.55b0` |  |
| `opentelemetry-instrumentation-sqlalchemy>=0.55b0` |  |
| `opentelemetry-instrumentation-httpx>=0.55b0` |  |

### `sentry`

| Requirement | Note |
|---|---|
| `sentry-sdk>=2.0` |  |

### `seed`

| Requirement | Note |
|---|---|
| `global-land-mask` |  |

### `kms`

| Requirement | Note |
|---|---|
| `boto3>=1.34` | AWS KMS |
| `google-cloud-kms>=2.21` | GCP KMS |

### `all`

| Requirement | Note |
|---|---|
| `climate-platform[api,ingest,train,otel]` |  |

### `dev`

| Requirement | Note |
|---|---|
| `pytest>=8.0` |  |
| `arelle-release>=2.45` | XBRL processor: validates S.27.01.01 instances against EIOPA's taxonomy and rules (scripts/validate_s2701_xbrl.py) |
| `pytest-asyncio>=0.23` | XBRL processor: validates S.27.01.01 instances against EIOPA's taxonomy and rules (scripts/validate_s2701_xbrl.py) |
| `httpx>=0.27` |  |
| `ruff==0.16.6` | XBRL processor: validates S.27.01.01 instances against EIOPA's taxonomy and rules (scripts/validate_s2701_xbrl.py) |

## 3. Web dependencies

Declared in `web/package.json`; *Resolved* is the version `web/package-lock.json` pins.

| Package | Declared | Resolved | Used for |
|---|---|---|---|
| `@tanstack/react-query` | ^5.101.4 | 5.101.4 | runtime |
| `@xyflow/react` | ^12.11.2 | 12.11.2 | runtime |
| `clsx` | ^2.1.1 | 2.1.1 | runtime |
| `framer-motion` | ^12.42.2 | 12.42.2 | runtime |
| `h3-js` | ^4.5.0 | 4.5.0 | runtime |
| `leaflet` | ^1.9.4 | 1.9.4 | runtime |
| `lucide-react` | ^1.27.0 | 1.27.0 | runtime |
| `maplibre-gl` | ^6.0.0 | 6.0.0 | runtime |
| `react` | ^19.2.7 | 19.2.8 | runtime |
| `react-dom` | ^19.2.7 | 19.2.8 | runtime |
| `react-leaflet` | ^5.0.0 | 5.0.0 | runtime |
| `react-router-dom` | ^7.18.1 | 7.18.1 | runtime |
| `recharts` | ^3.10.1 | 3.10.1 | runtime |
| `@tailwindcss/vite` | ^4.3.3 | 4.3.3 | build / dev |
| `@types/leaflet` | ^1.9.21 | 1.9.21 | build / dev |
| `@types/node` | ^24.13.2 | 24.13.3 | build / dev |
| `@types/react` | ^19.2.17 | 19.2.17 | build / dev |
| `@types/react-dom` | ^19.2.3 | 19.2.3 | build / dev |
| `@vitejs/plugin-react` | ^6.0.3 | 6.0.4 | build / dev |
| `oxlint` | ^1.71.0 | 1.76.0 | build / dev |
| `tailwindcss` | ^4.3.3 | 4.3.3 | build / dev |
| `typescript` | ~6.0.2 | 6.0.3 | build / dev |
| `vite` | ^8.1.1 | 8.1.5 | build / dev |

Scripts: `npm run dev` → `vite`, `npm run build` → `tsc -b && vite build`, `npm run lint` → `oxlint`, `npm run preview` → `vite preview`, `npm run test` → `node --test tests/*.test.ts`.

## 4. Services and processes

### API

FastAPI application `api/main.py`. Its OpenAPI schema (`app.openapi()`) lists **653 operations on 576 paths**; routes registered with `include_in_schema=False` (such as `/metrics`) are not counted. Operations per tag:

| Tag | Operations |
|---|---|
| Regulator portal | 53 |
| Agriculture / Supply chain | 42 |
| Reporting cockpit | 39 |
| Integration | 35 |
| Asset Management — Funds | 32 |
| EUDR | 32 |
| Regulatory tasks | 28 |
| Admin | 25 |
| Governance | 25 |
| Banking | 19 |
| Me | 18 |
| Insurance | 17 |
| Auth | 16 |
| Platform operator | 15 |
| European ESG Template (EET) | 14 |
| Transmission | 13 |
| onboarding | 13 |
| Supervisor | 12 |
| scim | 12 |
| Asset Management | 11 |
| Prior filings | 11 |
| Real Estate | 11 |
| Regulatory changes | 10 |
| Forward-risk decisions | 9 |
| passkeys · esign | 9 |
| sso | 9 |
| Entity-structure import | 8 |
| Meta | 8 |
| Loss | 6 |
| Realized exposure | 6 |
| Scores | 6 |
| periods | 6 |
| Approvals | 5 |
| Regulatory Packages | 5 |
| Service Portal | 5 |
| security | 5 |
| Analytics | 4 |
| Commodity price indices | 4 |
| Contracts | 4 |
| Drill-through | 4 |
| General-ledger reconciliation | 4 |
| Platform | 4 |
| Provided data (Lane 2) | 4 |
| Read API (Export & Connect) | 4 |
| Regulatory notifications | 4 |
| Seasonal-arrears overlay | 4 |
| Calc settings | 3 |
| Locations | 3 |
| Regulatory specifications | 3 |
| growth | 3 |
| ESRS statement | 2 |
| Health | 2 |
| Insurance — Solvency II documents | 2 |
| Lookup | 2 |
| Platform Info | 2 |
| Geo | 1 |

### Database

PostgreSQL through SQLAlchemy 2 and psycopg 3 (`postgresql+psycopg://`, setting `DATABASE_URL`). The schema is built only by the Alembic migrations — see [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md).

### Background workers

Celery application `services/tasks/celery_app.py`, broker and result backend from setting `REDIS_URL`. Periodic tasks (`celery_app.conf.beat_schedule`):

| Entry | Task | Schedule |
|---|---|---|
| `controls-test-sweep-daily` | `controls.test_sweep` | cron `30 6 * * *` |
| `drain-email-outbox` | `emails.drain_outbox` | every 120 s |
| `intake-drop-folder-sweep` | `intake.sweep_drop_folders` | every 300 s |
| `intake-observe-books` | `intake.observe_books` | cron `20 * * * *` |
| `kri-observe-sweep` | `kri.observe_sweep` | cron `0 * * * *` |
| `rebuild-geo-priors-daily` | `supervision.rebuild_geo_priors` | cron `30 4 * * *` |
| `recheck-decision-watchlist` | `decisions.recheck_watchlist` | cron `30 6 * * *` |
| `refresh-due-golden-source-feeds` | `feeds.refresh_due` | cron `0 * * * *` |
| `reg-alert-sweep-daily` | `reg.alert_sweep` | cron `45 5 * * *` |
| `reg-signals-sweep-daily` | `reg.signals_sweep` | cron `30 5 * * *` |
| `scan-eurlex-daily` | `reg.scan_eurlex` | cron `15 5 * * *` |
| `supervision-deadline-sweep-daily` | `supervision.deadline_sweep` | cron `0 6 * * *` |

### Web application

React single-page application built with Vite (`web/`); routes, navigation and role gating are in [APP_FLOW.md](APP_FLOW.md), the visual system in [DESIGN_BRIEF.md](DESIGN_BRIEF.md).

## 5. Configuration

Fields of `Settings` in `core/config.py` (read from the environment / `.env`). Values are not reproduced.

| Setting | Type | Note |
|---|---|---|
| `DATABASE_URL` | str |  |
| `STORAGE_PROVIDER` | str | local \| s3 \| gcs \| azure |
| `STORAGE_BUCKET` | str |  |
| `STORAGE_LOCAL_PATH` | str |  |
| `LIVE_DATA_PATH` | str |  |
| `H3_RESOLUTION` | int |  |
| `FIRMS_API_KEY` | str |  |
| `COPERNICUS_USER` | str |  |
| `COPERNICUS_PASSWORD` | str |  |
| `SENTINEL_HUB_CLIENT_ID` | str |  |
| `SENTINEL_HUB_CLIENT_SECRET` | str |  |
| `NEWS_API_KEY` | str |  |
| `REDIS_URL` | str |  |
| `CDSAPI_URL` | str |  |
| `CDSAPI_KEY` | str |  |
| `NASS_API_KEY` | str | USDA NASS Quick Stats (sub-national US yields) — .env only, never committed |
| `USDA_FAS_API_KEY` | str | api.data.gov key for USDA FAS PSD — .env only, never committed |
| `ADSAPI_URL` | str |  |
| `ADSAPI_KEY` | str |  |
| `OPENAQ_API_KEY` | str |  |
| `MLFLOW_TRACKING_URI` | str |  |
| `APP_ENV` | str |  |
| `LOG_LEVEL` | str |  |
| `SECRET_KEY` | str |  |
| `JWT_ALGORITHM` | str |  |
| `JWT_EXPIRATION_HOURS` | int |  |
| `ACCESS_TOKEN_MINUTES` | int |  |
| `REFRESH_TOKEN_DAYS` | int |  |
| `APP_ENCRYPTION_KEY` | str |  |
| `KMS_PROVIDER` | str |  |
| `KMS_KEY_ID` | str | KEK id/ARN (AWS) or crypto-key resource name (GCP) — for wrapping |
| `KMS_ENCRYPTED_DATA_KEY` | str | base64 of the KMS-encrypted data key (the only stored key material) |
| `KMS_REGION` | str | AWS region for the KMS client (optional) |
| `SENTRY_DSN` | str |  |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | str |  |
| `OTEL_SERVICE_NAME` | str |  |
| `SLO_LATENCY_BUDGET_S` | float |  |
| `STRIPE_API_KEY` | str |  |
| `DOCUSIGN_API_KEY` | str |  |
| `INTAKE_STORAGE_BACKEND` | str |  |
| `INTAKE_STORAGE_DIR` | str |  |
| `INTAKE_MAX_BYTES` | int | a single file above this is refused before parsing |
| `INTAKE_DROP_BACKEND` | str | drop-folder inbox; object storage = go-live #12/#13 |
| `INTAKE_DROP_DIR` | str | drop-folder channels: &lt;dir&gt;/&lt;org&gt;/&lt;template&gt;/incoming |
| `INTAKE_DROP_MIN_AGE_SECONDS` | int | a file untouched this long is complete (still-arriving files wait) |
| `INTAKE_RETENTION_DAYS` | int | ~7 years: kept as evidence behind filings |
| `CLAMD_HOST` | str |  |
| `CLAMD_PORT` | int |  |
| `CLAMD_SOCKET` | str |  |
| `INTAKE_REQUIRE_MALWARE_SCAN` | Optional[bool] |  |
| `AUDIT_RETENTION_DAYS` | int |  |
| `USDA_MARS_API_KEY` | str |  |
| `CORS_ORIGINS` | str |  |
| `KEY_BOOTSTRAP_SECRET` | str |  |
| `NOMINATIM_URL` | str |  |
| `NOMINATIM_MIN_INTERVAL_S` | float |  |
| `EMAIL_TRANSPORT` | str |  |
| `EMAIL_FROM` | str |  |
| `APP_BASE_URL` | str |  |
| `SMTP_HOST` | str |  |
| `SMTP_PORT` | int |  |
| `SMTP_USER` | str |  |
| `SMTP_PASSWORD` | str |  |
| `SMTP_STARTTLS` | bool |  |
| `GEOCODER_PROVIDER` | str |  |

## 6. Build and quality gate

### Before every commit: `scripts/precommit.sh`

Runs in order and stops at the first failure ([ENGINEERING_PROCESS.md §2](ENGINEERING_PROCESS.md)):

1. lint (whole repository, exactly as CI)
2. migration graph
3. applied migrations match their files (the development database)
4. migration round-trip (every revision up and down, on a scratch database)
5. project documents match the code (BACKEND_SCHEMA, TECHNICAL_REQUIREMENTS, APP_FLOW, DESIGN_BRIEF)
6. web build
7. web unit tests
8. data folders the tests read (E194: a worktree links the main checkout's git-ignored data)
9. test suite (+ demo-data guard)
10. running code

### Continuous integration: `.github/workflows/ci.yml`

Runs on push to main, develop; pull_request to main.

| Job | Needs | Runs when | Steps |
|---|---|---|---|
| `unit-tests` (Unit tests) |  | every run | actions/checkout@v4 → Set up Python → Install dependencies → Check migration graph (single head, no dangling links) → Run unit tests |
| `integration-tests` (Integration tests) | unit-tests | every run | actions/checkout@v4 → Set up Python → Install dependencies → Migration round-trip (every revision up and down, schema restored exactly) → Build schema (migrations to head — the app's real startup path) → Run integration tests |
| `lint` (Lint (ruff)) |  | every run | actions/checkout@v4 → Set up Python → Install ruff (the exact version pyproject.toml pins for dev) → Run ruff |
| `web` (Web build & unit tests) |  | every run | actions/checkout@v4 → Set up Node → Install dependencies → Build (tsc -b + vite) → Unit tests (node --test) |
| `build-push` (Build & push image) | unit-tests, integration-tests, lint, web | `github.ref == 'refs/heads/main' && github.event_name == 'push'` | actions/checkout@v4 → Log in to GitHub Container Registry → Set up Docker Buildx → Build and push API image → Build and push worker image |
| `deploy` (Deploy to k8s) | build-push | `github.ref == 'refs/heads/main' && github.event_name == 'push'` | Is a production cluster configured? → actions/checkout@v4 → Set up kubectl → Configure kubeconfig → Update image tags in manifests → Apply manifests → Wait for rollout |

## 7. Deployment artefacts

How these fit together: [SOFTWARE_DESCRIPTION.md §7](SOFTWARE_DESCRIPTION.md#7-deployment--infrastructure).

Container build stages (`infra/docker/Dockerfile`):

| Stage | Built from |
|---|---|
| `base` | `python:3.14-slim` |
| `api-deps` | `base` |
| `api` | `api-deps` |
| `ingest-deps` | `base` |
| `worker` | `ingest-deps` |

Compose services:

| File | Service | Image | Ports |
|---|---|---|---|
| `docker-compose.yml` | db | `timescale/timescaledb:latest-pg16` | 5433:5432 |
| `docker-compose.yml` | adminer | `adminer:latest` | 8080:8080 |
| `docker-compose.yml` | mlflow | `python:3.11-slim` | 5001:5001 |
| `infra/docker/docker-compose.prod.yml` | api | `climate-platform-api:${IMAGE_TAG:-latest}` | ${API_PORT:-8000}:8000 |
| `infra/docker/docker-compose.prod.yml` | scorer | `climate-platform-worker:${IMAGE_TAG:-latest}` |  |
| `infra/docker/docker-compose.prod.yml` | mlflow | `python:3.11-slim` | 5001:5001 |

Kubernetes manifests (`infra/k8s/`; applied by the CI deploy job only when a cluster is configured):

| File | Kind | Name | Schedule |
|---|---|---|---|
| `infra/k8s/api-deployment.yaml` | Deployment | climate-api |  |
| `infra/k8s/api-deployment.yaml` | Service | climate-api |  |
| `infra/k8s/api-deployment.yaml` | HorizontalPodAutoscaler | climate-api-hpa |  |
| `infra/k8s/ingestion-cronjob.yaml` | CronJob | satellite-ingestion | `0 5 * * *` |
| `infra/k8s/ingestion-cronjob.yaml` | CronJob | reg-monitoring | `0 2 * * *` |
| `infra/k8s/ingestion-cronjob.yaml` | CronJob | price-ingestion | `0 4 * * 1` |
| `infra/k8s/ingress.yaml` | Ingress | climate-api-ingress |  |
| `infra/k8s/namespace.yaml` | Namespace | climate-platform |  |
| `infra/k8s/scorer-cronjob.yaml` | CronJob | scorer-flood | `0 6 * * *` |
| `infra/k8s/scorer-cronjob.yaml` | CronJob | scorer-wildfire | `30 6 * * *` |
| `infra/k8s/scorer-cronjob.yaml` | CronJob | scorer-heat | `0 7 * * *` |
| `infra/k8s/secret.yaml` | Secret | climate-platform-secrets |  |

## 8. Security, observability and non-functional requirements

- Security, multi-tenancy and access control: [SOFTWARE_DESCRIPTION.md §6](SOFTWARE_DESCRIPTION.md#6-security-multi-tenancy--access-control).
- External interfaces and export formats: [SOFTWARE_DESCRIPTION.md §8](SOFTWARE_DESCRIPTION.md#8-external-interfaces).
- Observability: `docs/observability/` — `RUNBOOK.md`, `CAPACITY.md` and `slo.yaml`.

The service-level targets `docs/observability/slo.yaml` holds. Its header says what they are:

> Tellumen — Service Level Objectives (SLOs) Machine-readable target spec. These are INTERNAL design targets we build to; they become a published, contractual SLA only when the product is client-ready. SLIs are emitted by api/observability.py to /metrics (http_slo_events_total{sli,outcome} and http_request_duration_seconds); an error budget is 1 - objective over the rolling window. See RUNBOOK.md for alerting and incident response.

| Target | Value |
|---|---|
| SLO `availability` | objective 0.999, error_budget 0.001, filing_window_objective 0.9995 |
| SLO `latency_api` | budget_seconds 1.0, objective 0.99 |
| latency `any_address_score` | p95_s 3.0, p99_s 6.0 |
| latency `api_read` | p95_s 0.4 |
| latency `filing_export` | p95_s 10.0 |
| latency `async_hazard_jobs` | best_effort True |
| recovery `rto_hours` | 4 |
| recovery `rto_hours_filing_window` | 1 |
| recovery `rpo_minutes` | 15 |
| recovery `rpo_minutes_golden_source` | 5 |

Non-functional characteristics as [SOFTWARE_DESCRIPTION.md §9](SOFTWARE_DESCRIPTION.md#9-non-functional-characteristics) states them (quoted):

> TBD — no verified SLAs, throughput, or scaling benchmarks exist yet. Do not populate this section
> with estimates; fill in once real numbers (load tests, prod metrics) exist.
