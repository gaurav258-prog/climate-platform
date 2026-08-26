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

from core.db.config import check_db_connection, init_db

# Core routers (scores/locations/packages/auth) — must not be coupled to optional
# features. Each optional router is imported separately so a missing optional
# dependency (e.g. bs4 for the regulatory scraper) cannot take down the core API.
try:
    from api.routers import assetmgmt as assetmgmt_router
    from api.routers import auth, locations, lookup, packages, scores
    from api.routers import bank as bank_router
    from api.routers import bank_submissions as bank_submissions_router
    from api.routers import calc_settings as calc_settings_router
    from api.routers import funds as funds_router
    from api.routers import insurance as insurance_router
    from api.routers import platform as platform_router
    from api.routers import realestate as realestate_router
    from api.routers import realized as realized_router
    from api.routers import source_systems as source_systems_router
    from api.routers import supply as supply_router
    ROUTERS_AVAILABLE = True
except ImportError:
    ROUTERS_AVAILABLE = False

# Auth/RBAC/admin routers — separately guarded so a missing auth dependency
# (bcrypt/PyJWT) cannot take down the core scoring API. Login is guarded apart
# from the admin/approvals/portal set so each can land independently.
try:
    from api.routers import auth_user
    AUTH_USER_AVAILABLE = True
except ImportError:
    AUTH_USER_AVAILABLE = False

try:
    from api.routers import admin as admin_router
    from api.routers import analytics as analytics_router
    from api.routers import approvals as approvals_router
    from api.routers import arrears as arrears_router
    from api.routers import contracts as contracts_router
    from api.routers import decisions as decisions_router
    from api.routers import export_api as export_api_router
    from api.routers import filings as filings_router
    from api.routers import gl as gl_router
    from api.routers import growth as growth_router
    from api.routers import ingest as ingest_router
    from api.routers import meta as meta_router
    from api.routers import notifications as notifications_router
    from api.routers import onboarding_intake as onboarding_intake_router
    from api.routers import passkeys_esign as passkeys_esign_router
    from api.routers import ops_console as ops_console_router
    from api.routers import portal as portal_router
    from api.routers import prices as prices_router
    from api.routers import prior_filings as prior_filings_router
    from api.routers import provided as provided_router
    from api.routers import reg_changes as reg_changes_router
    from api.routers import reg_tasks as reg_tasks_router
    from api.routers import security_admin as security_admin_router
    from api.routers import sso_scim as sso_scim_router
    from api.routers import transmission as transmission_router
    from api.routers import webhooks as webhooks_router
    ADMIN_ROUTERS_AVAILABLE = True
except ImportError:
    ADMIN_ROUTERS_AVAILABLE = False

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

from core.config import settings as _settings

# In development allow all origins for convenience; otherwise restrict to the
# configured allowlist (CORS_ORIGINS). PATCH is required by the admin endpoints.
_cors_origins = (
    ["*"] if _settings.APP_ENV == "development"
    else [o.strip() for o in _settings.CORS_ORIGINS.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# ── Observability: metrics, structured access logs, optional Sentry ─────
try:
    from api.observability import (
        ObservabilityMiddleware,
        SecurityHeadersMiddleware,
        init_sentry,
        metrics_response,
    )
    init_sentry()
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return metrics_response()
except ImportError:
    pass

# ── Routers ────────────────────────────────────────────────────────────
if ROUTERS_AVAILABLE:
    app.include_router(auth.router)
    app.include_router(scores.router)
    app.include_router(locations.router)
    app.include_router(packages.router)
    app.include_router(platform_router.router)
    app.include_router(bank_router.router)
    app.include_router(bank_submissions_router.router)
    app.include_router(supply_router.router)
    app.include_router(insurance_router.router)
    app.include_router(realestate_router.router)
    app.include_router(assetmgmt_router.router)
    app.include_router(funds_router.router)
    app.include_router(calc_settings_router.router)
    app.include_router(realized_router.router)
    app.include_router(source_systems_router.router)
    app.include_router(lookup.router)

if AUTH_USER_AVAILABLE:
    app.include_router(auth_user.router)
    from api.routers import tasks as tasks_router
    app.include_router(tasks_router.router)

if ADMIN_ROUTERS_AVAILABLE:
    app.include_router(admin_router.router)
    app.include_router(contracts_router.router)
    app.include_router(approvals_router.router)
    app.include_router(filings_router.router)
    app.include_router(reg_tasks_router.router)
    app.include_router(decisions_router.router)
    app.include_router(analytics_router.router)
    app.include_router(notifications_router.router)
    app.include_router(gl_router.router)
    app.include_router(arrears_router.router)
    app.include_router(prices_router.router)
    app.include_router(export_api_router.router)
    app.include_router(provided_router.router)
    app.include_router(transmission_router.router)
    app.include_router(reg_changes_router.router)
    app.include_router(meta_router.router)
    app.include_router(portal_router.router)
    app.include_router(ingest_router.router)
    app.include_router(webhooks_router.router)
    app.include_router(prior_filings_router.router)
    app.include_router(ops_console_router.router)
    app.include_router(onboarding_intake_router.router)
    app.include_router(sso_scim_router.router)
    app.include_router(sso_scim_router.scim_router)
    app.include_router(security_admin_router.router)
    app.include_router(growth_router.router)
    app.include_router(passkeys_esign_router.router)


# ── Core Health & Info Endpoints ────────────────────────────────────────

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
    """Liveness + a real DB probe. 'ok' when the database answers, 'degraded'
    only when it genuinely doesn't (the probe uses text(), not a raw string)."""
    from sqlalchemy import text as _text

    from core.db.session import get_session
    try:
        with get_session() as s:
            s.execute(_text("SELECT 1"))
        db_state = "connected"
    except Exception as exc:  # genuine DB outage
        logger.error("health DB probe failed: %s", exc)
        return {"status": "degraded", "version": app.version, "database": "unavailable"}
    return {"status": "ok", "version": app.version, "database": db_state}


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
