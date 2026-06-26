"""
Climate Intelligence Platform — FastAPI application.

PHASE 0: Foundation API
- Health checks and platform info
- Database connectivity verification
- Regulatory framework endpoints
- CRCS (Continuous Regulatory Compliance Service) monitoring

Planned V1 Endpoints:
  /v1/scores/cell/{h3_cell}          — score for a specific H3 cell
  /v1/scores/portfolio               — all scores for customer's locations
  /v1/locations                      — asset location registry
  /v1/regulatory/changes             — regulatory change monitoring
  /v1/compliance/status              — compliance status by framework

Auth: X-Customer-Id header (Sprint 7 shim) → JWT/API-key auth (Sprint 8)
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.db.config import engine, get_db, check_db_connection, init_db
from core.db.models_regulatory_complete import Base

# Existing routers (keep)
try:
    from api.routers import auth, locations, packages, scores
    ROUTERS_AVAILABLE = True
except ImportError:
    ROUTERS_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    logger.info("🚀 Climate Intelligence Platform (Phase 0) starting up...")
    try:
        if check_db_connection():
            logger.info("✅ Database connection verified")
            init_db()
            logger.info("✅ Database tables initialized")
        else:
            logger.error("⚠️  Database not available - running in read-only mode")
    except Exception as e:
        logger.error(f"❌ Startup warning: {e}")

    yield

    logger.info("🛑 Climate Intelligence Platform shutting down...")


app = FastAPI(
    title="Climate Intelligence Platform",
    description=(
        "Regulatory compliance & climate risk assessment for financial institutions. "
        "Phase 0: Multi-framework support (TCFD, EU Taxonomy, SEC, Basel III, EBA/ECB, FCA) "
        "with automated regulatory change detection (CRCS) and N-1 versioning."
    ),
    version="0.1.0-alpha",
    contact={"name": "Climate Intelligence Platform Team"},
    license_info={"name": "Proprietary"},
    openapi_tags=[
        {"name": "Health",                "description": "Health checks and status"},
        {"name": "Platform Info",         "description": "Platform capabilities and status"},
        {"name": "Regulatory Monitoring", "description": "CRCS - Regulatory change detection"},
        {"name": "Compliance Status",     "description": "Multi-framework compliance tracking"},
    ],
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to customer domains in Sprint 8
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────
if ROUTERS_AVAILABLE:
    app.include_router(auth.router)
    app.include_router(scores.router)
    app.include_router(locations.router)
    app.include_router(packages.router)


# ── Core Health & Info Endpoints ────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Health check endpoint - verifies API and database connectivity"""
    try:
        db: Session = next(get_db())
        db.execute("SELECT 1")
        db.close()
        return {
            "status": "healthy",
            "version": "0.1.0-alpha",
            "database": "connected",
            "phase": "Phase 0: Foundation"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "degraded",
            "version": "0.1.0-alpha",
            "database": "unavailable",
            "phase": "Phase 0: Foundation"
        }


@app.get("/", tags=["Platform Info"])
async def root() -> dict:
    """Root endpoint with platform information"""
    return {
        "name": "Climate Intelligence Platform",
        "version": "0.1.0-alpha",
        "phase": "Phase 0: Foundation",
        "docs": "/docs",
        "health": "/health",
        "info": "/info"
    }


@app.get("/info", tags=["Platform Info"])
async def platform_info() -> dict:
    """Detailed platform information and capabilities"""
    return {
        "platform": "Climate Intelligence Platform (RegTech)",
        "version": "0.1.0-alpha",
        "phase": "Phase 0: Foundation",
        "status": "development",
        "critical_deadline": "2026-01-11 (EBA/GL/2025/01 - 6 months)",
        "frameworks_supported": [
            "TCFD (Governance, Strategy, Risk, Metrics & Targets)",
            "EU Taxonomy (Activity alignment, DNSH criteria)",
            "SEC Climate Disclosure (Scope 1/2/3, Form 10-K)",
            "Basel III Climate (Portfolio risk, capital charges)",
            "EBA/ECB Guidelines (Credit risk, NGFS scenarios)",
            "UK FCA Climate (Double materiality, £5B+ AUM)"
        ],
        "architecture": {
            "database": "PostgreSQL 14+ with TimescaleDB, PostGIS, uuid-ossp",
            "api_framework": "FastAPI (async)",
            "orm": "SQLAlchemy 2.0",
            "multi_tenancy": "Organization-based (org_id isolation)",
            "versioning": "N-1 regulation version support",
            "change_detection": "CRCS (Continuous Regulatory Compliance Service)"
        },
        "data_models": {
            "organizations": "Multi-tenant financial institutions",
            "assets": "Bank asset inventory with climate exposure",
            "scenarios": "1.5°C, 2°C, 4°C climate pathways",
            "emissions": "GHG Scope 1/2/3 tracking",
            "risk_scores": "Physical + transition risk assessment",
            "regulatory": "Framework versioning, filing history, amendments",
            "compliance": "CRCS monitoring, change detection, module discovery"
        },
        "roadmap": {
            "phase_0": "Weeks 1-2: Database schema, ORM, FastAPI skeleton",
            "phase_1": "Weeks 2-6: Regulatory change detection (CRCS)",
            "phase_2": "Weeks 5-10: Version management & archive lifecycle",
            "phase_3": "Weeks 8-13: EBA/ECB processing layer (Jan 11 deadline)",
            "phase_4": "Weeks 10-15: Asset management & climate data integration",
            "phase_5": "Weeks 13-18: TCFD scenario modeling & reporting",
            "phase_6": "Weeks 16-20: Customer portal & real-time notifications",
            "phase_7": "Weeks 19-22: Testing, hardening, security audit",
            "phase_8": "Week 23+: Production deployment & customer onboarding"
        },
        "research_documents": [
            "REGULATORY_MATRIX_FINAL.md - Input/processing/output mapping",
            "REGULATORY_MAINTENANCE_ARCHITECTURE.md - CRCS system design",
            "BUILD_PLAN_COMPREHENSIVE.md - Week-by-week implementation",
            "PHASE_0_QUICK_START.md - Executable setup guide"
        ]
    }


# ── Error Handlers ──────────────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    logger.error(f"HTTP {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# ── Utility endpoints ─────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/v1/meta/hazards", tags=["Meta"])
def list_hazards() -> dict:
    return {
        "hazards": [
            {"id": "flood",      "label": "River / Pluvial Flooding",  "class": "acute"},
            {"id": "wildfire",   "label": "Wildfire / Forest Fire",    "class": "acute"},
            {"id": "heat_acute", "label": "Extreme Heat Event",        "class": "acute"},
        ]
    }


@app.get("/v1/meta/scenarios", tags=["Meta"])
def list_scenarios() -> dict:
    return {
        "scenarios": [
            {"id": "baseline",   "label": "NGFS Current Policies",       "framework": "NGFS Phase 4"},
            {"id": "orderly",    "label": "NGFS Net Zero 2050",          "framework": "NGFS Phase 4"},
            {"id": "disorderly", "label": "NGFS Disorderly Transition",  "framework": "NGFS Phase 4"},
            {"id": "hot_house",  "label": "NGFS Hot House World",        "framework": "NGFS Phase 4"},
        ]
    }


@app.get("/v1/meta/frameworks", tags=["Meta"])
def list_frameworks() -> dict:
    return {
        "frameworks": [
            {
                "id":       "ECB",
                "label":    "ECB Physical Climate Risk",
                "standard": "ECB Guide Nov 2020 + EBA Pillar 3 ESG (Jan 2023)",
                "tables":   ["T1 Geographic", "T2 Hazard Exposure", "T3 Scenario Sensitivity",
                             "T4 High-Risk Concentration", "T5 Methodology"],
                "xbrl":     False,
            },
            {
                "id":       "CSRD",
                "label":    "CSRD ESRS E1-9 Physical Risk",
                "standard": "Delegated Regulation EU 2023/2772, ESRS E1-9",
                "tables":   ["E1-9A Material Risks", "E1-9B Exposure by Class",
                             "E1-9C Financial Exposure", "E1-9D Adaptation",
                             "E1-9E Time Horizon", "E1-9F Double Materiality"],
                "xbrl":     True,
                "xbrl_taxonomy": "EFRAG ESRS Set 1 (2023-12-22)",
            },
        ]
    }
