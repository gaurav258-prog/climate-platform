FROM python:3.9-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal system deps — no GDAL (not needed for API or scorer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── api deps (no GDAL/rasterio — those are ingest-worker only) ──────────
FROM base AS api-deps

COPY pyproject.toml .
RUN pip install --upgrade pip \
    && pip install -e ".[api]"

# ── api image ─────────────────────────────────────────────────────────────
FROM api-deps AS api

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]

# ── ingest worker (needs GDAL + HDF5 + NetCDF) ──────────────────────────
FROM base AS ingest-deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev \
    libhdf5-dev libnetcdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --upgrade pip \
    && pip install -e ".[ingest,train]"

FROM ingest-deps AS worker

COPY . .

CMD ["python", "scripts/run_scoring_engine.py", "--hazard", "flood"]
