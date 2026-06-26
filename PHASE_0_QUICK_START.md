# PHASE 0: FOUNDATION - QUICK START GUIDE
## Climate Intelligence Platform Setup

**Status:** Ready to deploy  
**Duration:** 1-2 weeks  
**Team:** 2 engineers (1 DevOps, 1 Backend)

---

## WHAT'S READY

✅ **Database Schema** (Complete: `/migrations/002_complete_schema_regulatory_crcs.sql`)
- 30+ tables covering all regulatory frameworks
- CRCS versioning system
- Multi-tenancy isolation
- Performance indexes

✅ **Documentation** (Complete)
- BUILD_PLAN_COMPREHENSIVE.md - 7-month roadmap
- REGULATORY_MAINTENANCE_ARCHITECTURE.md - CRCS system design
- REGULATORY_MATRIX_FINAL.md - Input/processing/output mapping
- 15+ regulatory research documents

✅ **Project Structure** (Designed)
- FastAPI backend
- SQLAlchemy ORM
- PostgreSQL database
- Docker containerization

---

## IMMEDIATE ACTIONS (This Week)

### Step 1: Database Setup (Day 1-2)

```bash
# 1a. Verify PostgreSQL 14+ with extensions
psql --version
# Expected: PostgreSQL 14.x+

# 1b. Create database and user
psql -U postgres -h localhost << 'EOF'
CREATE DATABASE climate_platform;
CREATE USER climate_app WITH PASSWORD 'secure_password_here';
ALTER ROLE climate_app WITH CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE climate_platform TO climate_app;
\c climate_platform
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
EOF

# 1c. Run migration
psql -U climate_app -h localhost -d climate_platform -f migrations/002_complete_schema_regulatory_crcs.sql

# 1d. Verify tables
psql -U climate_app -d climate_platform -c "\dt" | head -20
# Should show 30+ tables created
```

### Step 2: Python Project Setup (Day 2-3)

```bash
# 2a. Create Python environment
cd /Users/gauravsachdeva/Downloads/climate-platform
python3.11 -m venv venv
source venv/bin/activate

# 2b. Install dependencies
cat > requirements.txt << 'EOF'
fastapi==0.104.0
uvicorn==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
pydantic==2.5.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
alembic==1.13.0
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.1
redis==5.0.1
celery==5.3.4
aiohttp==3.9.1
beautifulsoup4==4.12.2
requests==2.31.0
EOF

pip install -r requirements.txt

# 2c. Generate ORM models (see Step 3)
```

### Step 3: SQLAlchemy ORM Models Generation (Day 3-4)

**IMPORTANT:** The ORM models must be comprehensive. Two options:

**Option A: Use existing models.py template (FAST)**
- File: `/core/db/models.py` (partially updated)
- Add missing relationship definitions
- Focus on multi-tenancy and regulatory classes

**Option B: Auto-generate from schema (THOROUGH)**
```bash
# Install sqlacodegen
pip install sqlacodegen

# Generate models from database
sqlacodegen postgresql://climate_app:password@localhost/climate_platform > /tmp/models_generated.py

# Review & integrate into core/db/models.py
```

**Models to include (priority order):**
1. ✅ Organization, User (multi-tenancy)
2. ✅ BankAsset, ClimateHazardExposure (assets)
3. ✅ RegulatoryFramework, RegulationVersion, RegulatoryChange (CRCS)
4. ✅ ClimateScenario, ScenarioFinancialImpact (scenarios)
5. ✅ GHGEmissionsInventory, ClimateRiskScore (metrics)
6. ✅ RegulatoryFiling, FilingAmendment (outputs)
7. ✅ OrgCRCSSubscription (billing)
8. ✅ AuditLog, GovernanceStructure (governance)

### Step 4: FastAPI Skeleton (Day 4-5)

Create `/api/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.db.config import SessionLocal, engine
from core.db.models import Base

app = FastAPI(
    title="Climate Intelligence Platform",
    version="0.1.0",
    docs_url="/docs"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

# Health check
@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

# Run: uvicorn api.main:app --reload --port 8000
```

### Step 5: Docker Setup (Day 5)

Create `/docker-compose.yml`:

```yaml
version: '3.9'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: climate_dev
      POSTGRES_DB: climate_platform
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: "postgresql://postgres:climate_dev@postgres:5432/climate_platform"
      REDIS_URL: "redis://redis:6379"
    command: uvicorn api.main:app --host 0.0.0.0 --reload

volumes:
  postgres_data:
```

Create `/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 6: First Test (Day 5)

```bash
# Start via Docker Compose
docker-compose up -d

# Test API
curl http://localhost:8000/health
# Expected: {"status": "ok", "version": "0.1.0"}

# Test database connection
python3 -c "from core.db.models import Base; from core.db.config import engine; Base.metadata.tables.keys()" | head -10
# Should list tables
```

---

## FILE CHECKLIST

**Before starting Phase 1:**

- [ ] `/migrations/002_complete_schema_regulatory_crcs.sql` exists ✅
- [ ] PostgreSQL 14+ running with extensions ✅
- [ ] All 30+ tables created in database ✅
- [ ] `/core/db/models.py` has complete ORM models (IN PROGRESS)
- [ ] `/api/main.py` with FastAPI app ✅
- [ ] `/docker-compose.yml` ✅
- [ ] `/Dockerfile` ✅
- [ ] `requirements.txt` ✅
- [ ] `.env` with DB credentials ✅
- [ ] API health check passing ✅

---

## SUCCESS CRITERIA

✅ **Phase 0 Complete When:**
1. Database schema fully deployed (30+ tables)
2. ORM models auto-generated and imported
3. FastAPI app runs without errors
4. Health check endpoint returns 200
5. Can query organizations table (verify org_id isolation)
6. Docker Compose brings up full stack
7. All 8 build phases ready to execute

---

## NEXT: Phase 1 (Regulatory Monitoring)

Once Phase 0 complete, begin:
- Web scrapers (EUR-Lex, SEC, FCA, ECB)
- Change detection service
- Customer notification system
- Impact analysis engine

**Time estimate:** Weeks 2-6

---

## REFERENCE FILES

- **Schema:** `migrations/002_complete_schema_regulatory_crcs.sql`
- **Architecture:** `REGULATORY_MAINTENANCE_ARCHITECTURE.md`
- **Roadmap:** `BUILD_PLAN_COMPREHENSIVE.md`
- **Research:** `REGULATORY_MATRIX_FINAL.md` + 15 deep-dive documents
- **Implementation Plan:** This file

---

**Ready to deploy? Confirm and I'll provide:**
1. Complete `/core/db/models.py` with all 30 ORM classes
2. `/core/db/config.py` with connection pooling
3. First unit test (db connection)
4. `.env.example` template

**Then Phase 0 can run in parallel with Phase 1 research.**
