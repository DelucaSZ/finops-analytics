from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.routes import accounts, auth, dashboard, findings, policies, scans
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.demo import seed_demo_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.demo_mode:
        with SessionLocal() as db:
            seed_demo_data(db)
    yield


app = FastAPI(
    title="NuvemIQ API",
    description="Multi-account AWS FinOps analysis API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(scans.router, prefix="/api/v1")
app.include_router(findings.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nuvemiq-api"}
