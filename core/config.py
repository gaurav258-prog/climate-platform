from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # tolerate env vars not declared here (ops/deploy keys)
    )

    # Database — default matches .env identity + driver (psycopg3). The real
    # value comes from .env; this is only the fallback when none is set.
    DATABASE_URL: str = "postgresql+psycopg://platform@localhost:5432/climate"

    # Storage — cloud-agnostic
    STORAGE_PROVIDER: str = "local"  # local | s3 | gcs | azure
    STORAGE_BUCKET: str = "climate-platform-dev"
    STORAGE_LOCAL_PATH: str = "./data/storage"

    # H3 — committed to resolution 8 for EU MVP (~0.7km² cells)
    H3_RESOLUTION: int = 8

    # Satellite API keys
    FIRMS_API_KEY: str = ""
    COPERNICUS_USER: str = ""
    COPERNICUS_PASSWORD: str = ""
    # Copernicus Data Space — Sentinel Hub (Process/Statistical API). OAuth2 client-credentials pair created
    # in the CDSE dashboard (separate from the OData username/password above). When set, the Sentinel-1 SAR
    # adapter computes per-H3-cell VV backscatter server-side via the Statistical API — no SNAP, no scene
    # downloads. Empty = the adapter stays in stub/planned mode (nothing lands). See services/ingestion/adapters/sentinel1_sar.py.
    SENTINEL_HUB_CLIENT_ID: str = ""
    SENTINEL_HUB_CLIENT_SECRET: str = ""

    # Regulatory-news early-signal feed (services/regulatory_monitoring/scrapers/news_aggregator.py).
    # Empty = the free, keyless GDELT DOC 2.0 index is used. Set NEWS_API_KEY to use NewsAPI.org instead.
    NEWS_API_KEY: str = ""

    # Redis — Celery broker + result backend for the gridded on-demand hazard
    # jobs (durability upgrade from FastAPI BackgroundTasks; see services/tasks/).
    # Was already in .env but never actually declared here, so it was silently
    # ignored by pydantic-settings (extra="ignore") — a real orphaned config
    # value, not a working integration, until now.
    REDIS_URL: str = "redis://localhost:6379/0"

    # Copernicus Climate Data Store (ERA5, GloFAS)
    CDSAPI_URL: str = "https://cds.climate.copernicus.eu/api"
    CDSAPI_KEY: str = ""

    # Copernicus Atmosphere Data Store (CAMS) — a SEPARATE service from CDS
    # (different host), confirmed to share the same personal access token as
    # CDS post the 2024 ECMWF unification (verified live 2026-07-03).
    ADSAPI_URL: str = "https://ads.atmosphere.copernicus.eu/api"
    ADSAPI_KEY: str = ""

    # OpenAQ v3 — ground-station calibration/validation layer for pollution
    OPENAQ_API_KEY: str = ""

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Auth / JWT — names match .env.example. The default secret is DEV-ONLY;
    # in any non-development env a real SECRET_KEY must come from the (gitignored)
    # .env or a secret manager. See _guard_secret() below.
    SECRET_KEY: str = "dev-insecure-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    # Short-lived access token + long-lived rotating refresh token (enterprise session model).
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 14
    # Envelope-encryption key for secrets at rest (OIDC client secret, etc.). A dedicated Fernet key
    # (urlsafe-b64, 32 bytes) belongs in the environment / KMS; absent, one is derived from SECRET_KEY.
    APP_ENCRYPTION_KEY: str = ""
    # Comma-separated allowed origins for CORS (used when APP_ENV != development).
    CORS_ORIGINS: str = "http://localhost:5175,http://localhost:5173"

    # API-key bootstrap: the no-auth "mint the first key" path is gated behind
    # this operator secret. EMPTY (the default) means anonymous bootstrap is
    # DISABLED entirely — the production-safe default. To onboard a customer,
    # set it and present it as the X-Bootstrap-Secret header. This closes the
    # hole where anyone could POST /v1/auth/keys with a customer UUID and mint a
    # live key with no authentication.
    KEY_BOOTSTRAP_SECRET: str = ""

    # Geocoder — defaults to OpenStreetMap's public Nominatim, which enforces a
    # max of 1 request/second. That is the hard bottleneck when pre-loading a
    # large issuer universe. Point NOMINATIM_URL at a self-hosted Nominatim (or a
    # paid geocoder's compatible endpoint) and drop NOMINATIM_MIN_INTERVAL_S to
    # 0 to scale — a config change, not a code change. Only raise loader
    # concurrency above 1 when pointed at such an instance (never against the
    # public server — it violates their usage policy).
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org/search"
    NOMINATIM_MIN_INTERVAL_S: float = 1.0

    # Email — outbound notifications (e.g. a task @mention pings the colleague by email).
    # EMAIL_TRANSPORT: "" = auto (smtp if SMTP_HOST is set, else off) | "smtp" | "console" | "off".
    #   console  — render + log the email without delivering (dev / demo); the outbox marks it sent.
    #   off      — record the intent only (status 'skipped'); no delivery. The production default until
    #              SMTP is configured, so a missing mail server never blocks a comment.
    # SMTP_* come from the environment / secret manager — never committed. APP_BASE_URL builds the
    # deep-link back to the task in the email.
    EMAIL_TRANSPORT: str = ""
    EMAIL_FROM: str = "Tellumen <notifications@tellumen.local>"
    APP_BASE_URL: str = "http://localhost:5183"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    # Which geocoding backend the cache-aware layer dispatches to. "nominatim" is the
    # only one implemented today; the seam lets a paid provider (google/here/mapbox) be
    # dropped in without touching call sites. Resolved geocodes are cached in Postgres
    # (geocode_cache) so repeated / bulk lookups don't re-hit the provider.
    GEOCODER_PROVIDER: str = "nominatim"


_DEV_SECRET = "dev-insecure-change-me"


def _guard_secret(s: "Settings") -> "Settings":
    """Fail fast if a real deployment is still using the dev secret."""
    if s.APP_ENV != "development" and s.SECRET_KEY == _DEV_SECRET:
        raise RuntimeError(
            "SECRET_KEY is still the insecure dev default but APP_ENV != development. "
            "Set a strong SECRET_KEY in the environment before starting the API."
        )
    return s


settings = _guard_secret(Settings())
