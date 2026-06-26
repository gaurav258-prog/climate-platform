# Getting Started: Production Setup (Option B - Parallel)

**Status:** Database schema designed, Flood adapters drafted, Ready for parallel implementation  
**Current Date:** 2026-06-26  
**Target:** Week 1 completion of DB + Flood data integration

---

## **Work Stream A: Database Setup** (Week 1)

### Prerequisites
- PostgreSQL 14+ installed locally or in the cloud
- TimescaleDB extension enabled
- PostGIS extension (for geospatial queries)

### Step 1: Install PostgreSQL + Extensions

**Local Development:**
```bash
# macOS
brew install postgresql@14 timescaledb

# Ubuntu
sudo apt-get install postgresql-14 postgresql-14-timescaledb postgis

# Or use Docker
docker run -d \
  --name climate-db \
  -e POSTGRES_PASSWORD=climate_dev_password \
  -e POSTGRES_DB=climate_platform \
  -p 5432:5432 \
  timescale/timescaledb:latest-pg14
```

### Step 2: Create Database and User

```sql
-- Connect as postgres user
psql -U postgres -h localhost

-- Create database
CREATE DATABASE climate_platform;

-- Create application user
CREATE USER climate_app WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE climate_platform TO climate_app;

-- Connect to new database
\c climate_platform

-- Enable extensions
CREATE EXTENSION timescaledb CASCADE;
CREATE EXTENSION postgis;
CREATE EXTENSION "uuid-ossp";
```

### Step 3: Run Migration

```bash
# Copy migration file
cp migrations/001_initial_schema.sql /path/to/migrations/

# Run migration
psql -U climate_app -h localhost -d climate_platform -f migrations/001_initial_schema.sql

# Verify tables created
psql -U climate_app -h localhost -d climate_platform \
  -c "\dt"
```

### Step 4: Install ORM and Database Libraries

```bash
# In climate-platform root
pip install sqlalchemy psycopg2-binary sqlalchemy-utils alembic
```

### Step 5: Create Database Config

**File:** `core/db/config.py`

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://climate_app:your_secure_password@localhost:5432/climate_platform"
)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Test connections before using
    echo=False  # Set to True for SQL query logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### **Checklist for Week 1**
- [ ] PostgreSQL 14 installed & running
- [ ] TimescaleDB & PostGIS extensions enabled
- [ ] Migration applied successfully
- [ ] All tables created (verify with `\dt`)
- [ ] ORM models written
- [ ] Database config integrated with FastAPI

---

## **Work Stream B: Flood Data Integration** (Week 1)

### Current Status
✅ **Flood adapters drafted:** `services/ingestion/adapters/flood_sources.py`

Contains:
- `ERA5PrecipitationAdapter` - Daily precipitation from ECMWF
- `EuropeaRiverGaugeAdapter` - Real-time water levels (6 major gauges)
- `Sentinel1FloodDetectionAdapter` - SAR flood detection
- Main `ingest_flood_data()` pipeline

### Step 1: Set Up API Credentials

**ERA5 (ECMWF Climate Data)**
1. Register: https://cds.climate.copernicus.eu/user/register
2. Get API key from user profile
3. Store as environment variable:
   ```bash
   export COPERNICUS_CDS_API_KEY="your_api_key"
   ```

**Sentinel-1 (Copernicus Open Access Hub)**
1. Register: https://scihub.copernicus.eu/
2. Use account for accessing SAR data (see code comments)
3. Store credentials:
   ```bash
   export COPERNICUS_SCIHUB_USER="your_email"
   export COPERNICUS_SCIHUB_PASSWORD="your_password"
   ```

**River Gauges (EEA - Free, no auth needed)**
- Data: https://www.eea.europa.eu/data-and-maps
- API: EUWIS (European Water Information System)

### Step 2: Implement Real Data Fetching

The current `flood_sources.py` has **placeholder/synthetic data**. Wire up real APIs:

**ERA5 Precipitation (Priority 1):**
```python
# Replace _parse_era5_netcdf() with real netCDF4 parsing
import xarray as xr
import cdsapi

client = cdsapi.Client()
request = {
    'product_type': 'reanalysis',
    'variable': 'total_precipitation',
    'year': '2025',
    'month': '06',
    'day': '25',
    'time': '00:00',
    'format': 'netcdf',
}
result = client.retrieve('era5-land-monthly-means', request, 'era5_data.nc')
ds = xr.open_dataset('era5_data.nc')
```

**River Gauges (Priority 2):**
```python
# Query EEA EUWIS API or national databases
# Example: Deutsche Gewässerkundliche Mitteilungen (DGM)
# https://www.bafg.de/EN
```

**Sentinel-1 SAR (Priority 3):**
```python
# Use sentinelsat library
from sentinelsat import SentinelAPI

api = SentinelAPI(user, password, 'https://scihub.copernicus.eu/dhus')
footprint = "POLYGON((...))"  # European bounding box
products = api.query(footprint, date=('20250625', '20250630'), producttype='GRD')
```

### Step 3: Create Scheduled Ingestion Job

**File:** `services/ingestion/scheduler.py`

```python
from apscheduler.schedulers.background import BackgroundScheduler
from services.ingestion.adapters.flood_sources import ingest_flood_data
from core.db.config import SessionLocal

scheduler = BackgroundScheduler()

# Run flood ingestion daily at 2 AM UTC (after ERA5 updates)
scheduler.add_job(
    lambda: ingest_flood_data(SessionLocal(), org_id="platform", era5_api_key=os.getenv("COPERNICUS_CDS_API_KEY")),
    'cron',
    hour=2,
    minute=0,
    id='flood_daily_ingest'
)

scheduler.start()
```

### Step 4: Add to FastAPI Startup

**File:** `services/seismic_api.py`

```python
from services.ingestion.scheduler import scheduler

@app.on_event("startup")
async def startup():
    """Start background data ingestion tasks."""
    if not scheduler.running:
        scheduler.start()
```

### **Checklist for Week 1**
- [ ] API credentials registered & stored
- [ ] Real data fetchers implemented (ERA5 → River Gauges → SAR)
- [ ] Flood observations stored in database
- [ ] Scheduled ingestion job created
- [ ] Errors logged & monitored
- [ ] Data quality checks added

---

## **Week 2: Connect API to Database**

Once both work streams are done:

1. **Create API endpoints** that query `flood_observations` table
2. **Wire React components** to consume real flood data
3. **Run daily ingestion** & verify data flows end-to-end

---

## **Environment Variables Setup**

Create `.env` file in project root:

```bash
# Database
DATABASE_URL="postgresql://climate_app:password@localhost:5432/climate_platform"

# API Keys
COPERNICUS_CDS_API_KEY="your_era5_key"
COPERNICUS_SCIHUB_USER="your_email"
COPERNICUS_SCIHUB_PASSWORD="your_password"

# App
ENVIRONMENT="development"
LOG_LEVEL="INFO"
```

---

## **Testing Data Flow**

Once DB + adapters are ready:

```python
# Test script: scripts/test_flood_ingestion.py
from sqlalchemy.orm import sessionmaker
from core.db.config import engine, SessionLocal
from services.ingestion.adapters.flood_sources import ingest_flood_data
import asyncio

async def test():
    db = SessionLocal()
    await ingest_flood_data(db, org_id="test", era5_api_key="...")
    
    # Verify data stored
    obs = db.query(FloodObservation).count()
    print(f"Stored {obs} flood observations")

asyncio.run(test())
```

---

## **Next Steps (After Week 1)**

1. **Week 2:** Wildfire data sources (FIRMS, Sentinel-2)
2. **Week 3:** Heat & Seismic data sources
3. **Week 3-4:** Compute risk scores from raw observations
4. **Week 4:** Wire API endpoints to database queries
5. **Week 4+:** Connect React components to real APIs

---

## **Troubleshooting**

### PostgreSQL Connection Fails
```bash
# Check if PostgreSQL is running
brew services list  # macOS
sudo systemctl status postgresql  # Linux

# Test connection
psql -U climate_app -h localhost -d climate_platform -c "SELECT 1"
```

### TimescaleDB Not Found
```bash
# Verify extension installed
psql -U climate_app -d climate_platform -c "\dx timescaledb"

# If missing, install on Ubuntu:
sudo apt-get install postgresql-14-timescaledb

# Then enable in PostgreSQL:
CREATE EXTENSION timescaledb;
```

### API Credential Issues
- ERA5: Verify key at https://cds.climate.copernicus.eu/user
- Sentinel: Test login at https://scihub.copernicus.eu/

---

## **Performance Notes**

- **Hypertables (TimescaleDB):** Automatically partition observations by time
- **Indexes:** Created on (org_id, timestamp) for 1000x+ query speedup
- **Connection Pooling:** 10 min + 20 overflow for concurrent requests
- **Data Retention:** Set up archival for >1 year old observations

---

**Ready to start?** Begin with Work Stream A (DB setup) while Work Stream B (code) develops in parallel. They converge at week 2 when we wire everything together.
