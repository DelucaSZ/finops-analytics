from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401
from app.api.routes import (
    accounts,
    audit,
    auth,
    billing,
    cloud_accounts,
    cloudwatch_cost,
    cloudwatch_usage,
    collections,
    dashboard,
    findings,
    finops_flow,
    finops_ledger,
    mfa,
    opportunities,
    opportunity_discovery,
    opportunity_history,
    opportunity_policy,
    policies,
    pricing,
    scans,
    tls,
    users,
)
from app.core.config import settings
from app.db.migrations import initialize_database
from app.db.session import SessionLocal, engine
from app.services.billing_profiles import ensure_finops_profile
from app.services.demo import seed_demo_data
from app.services.opportunity_policy import OpportunityManagementPolicyService


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(engine)
    with SessionLocal(bind=engine) as db:
        ensure_finops_profile(db)
        OpportunityManagementPolicyService.get_or_create(db)
        db.commit()
        if settings.demo_mode:
            seed_demo_data(db)
    yield


app = FastAPI(
    title="DeepOps API",
    description="Multi-account cloud FinOps analysis API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic errors can otherwise echo the submitted password/input in a 422 response.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ]
        },
    )


@app.middleware("http")
async def sensitive_response_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(
        (
            "/api/v1/auth",
            "/api/v1/users",
            "/api/v1/audit",
            "/api/v1/tls",
            "/api/v1/cloud-accounts",
            "/api/v1/pricing",
            "/api/v1/finops",
            "/api/v1/billing",
            "/api/v1/usage",
            "/api/v1/deepops-costs",
            "/api/v1/opportunity-history",
            "/api/v1/settings/opportunity-policy",
        )
    ):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(mfa.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(tls.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(cloud_accounts.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(pricing.router, prefix="/api/v1")
app.include_router(scans.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")
app.include_router(opportunity_discovery.router, prefix="/api/v1")
app.include_router(findings.router, prefix="/api/v1")
app.include_router(opportunities.router, prefix="/api/v1")
app.include_router(opportunity_history.router, prefix="/api/v1")
app.include_router(opportunity_policy.router, prefix="/api/v1")
app.include_router(finops_ledger.router, prefix="/api/v1")
app.include_router(finops_flow.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(cloudwatch_usage.router, prefix="/api/v1")
app.include_router(cloudwatch_cost.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nuvemiq-api"}
