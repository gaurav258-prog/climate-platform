from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Database
    DATABASE_URL: str = "postgresql://platform:devpassword@localhost:5432/climate"

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


settings = Settings()
