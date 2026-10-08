from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.errors import register_error_handlers
from app.core.logging import RequestIdMiddleware, setup_logging
from app.core.numbering import DocumentSequence
from app.modules.catalog.router import router as catalog_router
from app.modules.crm.router import router as crm_router
from app.modules.identity.router import router as identity_router
from app.modules.identity.service import IdentityService
from app.modules.organization.router import router as org_router
from app.modules.organization.service import OrganizationService
from app.modules.sales.router import router as sales_router

# Initialize structured logging
setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Bootstrap superuser, default settings, and initial document sequences
    with SessionLocal() as db:
        identity_svc = IdentityService(db)
        identity_svc.bootstrap_superuser()

        org_svc = OrganizationService(db)
        org_svc.get_or_create_settings()

        # Seed document sequences if not present (Roadmap §4.5)
        sequences = [
            DocumentSequence(
                doc_type="customer",
                prefix="CUS",
                include_year=False,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="employee",
                prefix="EMP",
                include_year=False,
                padding=4,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="lead",
                prefix="LEAD",
                include_year=False,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="opportunity",
                prefix="OPP",
                include_year=False,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="quote",
                prefix="QT",
                include_year=True,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="sales_order",
                prefix="SO",
                include_year=True,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="invoice",
                prefix="INV",
                include_year=True,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="credit_note",
                prefix="CN",
                include_year=True,
                padding=6,
                next_value=1,
            ),
            DocumentSequence(
                doc_type="payment",
                prefix="PAY",
                include_year=True,
                padding=6,
                next_value=1,
            ),
        ]
        for seq in sequences:
            existing = db.execute(
                select(DocumentSequence).where(DocumentSequence.doc_type == seq.doc_type)
            ).scalar_one_or_none()
            if not existing:
                db.add(seq)
        db.commit()

    yield
    # Shutdown logic if any


app = FastAPI(
    title="ERP/CRM Operational Core",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register request ID tracking middleware
app.add_middleware(RequestIdMiddleware)

# Register RFC 7807 problem+json error handlers
register_error_handlers(app)


# Observability endpoints (Roadmap §4.12)
@app.get("/health", tags=["Observability"])
def health_check() -> dict[str, str]:
    """Process liveness probe."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/ready", tags=["Observability"])
def readiness_check(response: Response) -> dict[str, str]:
    """Database connectivity readiness probe."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": f"disconnected: {exc}"}


# Mount API V1 routers
API_PREFIX = "/api/v1"
app.include_router(identity_router, prefix=API_PREFIX)
app.include_router(org_router, prefix=API_PREFIX)
app.include_router(crm_router, prefix=API_PREFIX)
app.include_router(catalog_router, prefix=API_PREFIX)
app.include_router(sales_router, prefix=API_PREFIX)
