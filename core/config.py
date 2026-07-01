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

    # Copernicus Climate Data Store (ERA5, GloFAS)
    CDSAPI_URL: str = "https://cds.climate.copernicus.eu/api"
    CDSAPI_KEY: str = ""

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
    # Comma-separated allowed origins for CORS (used when APP_ENV != development).
    CORS_ORIGINS: str = "http://localhost:5175,http://localhost:5173"


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
