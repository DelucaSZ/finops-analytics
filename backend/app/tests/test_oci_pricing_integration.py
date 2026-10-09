from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app import worker
from app.api.routes.opportunities import router
from app.db.base import Base
from app.db.session import get_db
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.oci_analyzers import OciBlockVolumeUnattachedAnalyzer
from app.services.oci_correlation_models import OciResourceAnalysisContext, OciResourceUsageContext
from app.services.oci_discovery_models import OciDiscoveredResource
from app.services.oci_pricing import OCI_PRICING_SOURCE, OCI_PRICING_VERSION

TENANCY_ID = "ocid1.tenancy.oc1..pricingintegration"
RESOURCE_ID = "ocid1.volume.oc1.sa-saopaulo-1.pricingintegration"
REGION = "sa-saopaulo-1"
COMPARTMENT_ID = "ocid1.compartment.oc1..pricingintegration"
START = datetime(2026, 10, 9, 12, tzinfo=UTC)


def _block_volume_finding(*, size_in_gbs: int, vpus_per_gb: int):
    inventory = OciDiscoveredResource(
        provider="oci",
        resource_id=RESOURCE_ID,
        resource_type="block_volume",
        name="pricing-integration-volume",
        region=REGION,
        compartment_id=COMPARTMENT_ID,
        lifecycle_state="AVAILABLE",
        freeform_tags={"Owner": "FinOps"},
        defined_tags={},
        sources=["block_storage_api"],
        attributes={
            "attachment_count": 0,
            "attachment_coverage": "complete",
            "size_in_gbs": size_in_gbs,
            "vpus_per_gb": vpus_per_gb,
        },
    )
    context = OciResourceAnalysisContext(
        resource_id=inventory.resource_id,
        inventory=inventory,
        relationships=[],
        native_recommendations=[],
        usage=OciResourceUsageContext(
            records=[],
            totals_by_currency={},
            period_start=START - timedelta(days=30),
            period_end=START,
        ),
        coverage={
            "inventory": "complete",
            "advisor": "complete",
            "usage": "complete",
            "monitoring": "complete",
        },
        inventory_coverage={"block_volume": "complete"},
        relationship_coverage={
            "volume_attachment": "complete",
            "boot_volume_attachment": "complete",
            "public_ip_assignment": "complete",
        },
        provenance={"inventory": ("block_storage_api",)},
    )
    return OciBlockVolumeUnattachedAnalyzer().analyze(context)[0]


def _create_run(db: Session, cloud_account: CloudAccount, *, started_at: datetime):
    scan = Scan(
        cloud_account_id=cloud_account.id,
        account_id=None,
        status="running",
        started_at=started_at,
    )
    db.add(scan)
    db.flush()
    run = CollectionRun(
        scan_id=scan.id,
        provider="oci",
        account_id=cloud_account.native_account_id,
        started_at=started_at,
        status=CollectionRunStatus.RUNNING,
    )
    db.add(run)
    db.flush()
    return scan, run


def test_oci_catalog_pricing_survives_persistence_api_and_financial_refresh():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        cloud_account = CloudAccount(
            provider="oci",
            native_account_id=TENANCY_ID,
            name="OCI Pricing Integration",
            enabled=True,
        )
        db.add(cloud_account)
        db.flush()

        first_scan, first_run = _create_run(db, cloud_account, started_at=START)
        first_finding = _block_volume_finding(size_in_gbs=500, vpus_per_gb=10)
        worker.persist_findings(
            db,
            first_scan,
            first_run,
            [first_finding],
            [first_finding.rule_key],
            observed_at=START,
        )
        db.commit()

        persisted = db.scalar(select(Finding).where(Finding.provider == "oci"))
        assert persisted is not None
        persisted_id = persisted.id
        persisted_fingerprint = persisted.fingerprint
        assert persisted.current_monthly_cost == Decimal("44.55")
        assert persisted.estimated_monthly_savings == Decimal("44.55")
        assert persisted.currency == "BRL"
        assert persisted.provider_metadata["financial_value_populated"] is True
        assert persisted.evidence["pricing"]["status"] == "priced"
        assert persisted.evidence["pricing"]["source"] == OCI_PRICING_SOURCE
        assert persisted.evidence["pricing"]["version"] == OCI_PRICING_VERSION
        assert persisted.evidence["pricing"]["currency"] == "BRL"

        admin = User(
            name="Admin",
            email="oci-pricing-admin@example.com",
            password_hash="unused",
            role="admin",
        )
        db.add(admin)
        db.commit()
        _, token = new_session(db, admin)
        db.commit()

    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as http:
        http.headers.update(
            {
                "Cookie": f"{COOKIE}={token}",
                "X-CSRF-Token": csrf_token(token),
                "X-DeepOps-Request": "1",
            }
        )
        response = http.get("/opportunities?provider=oci&page_size=10")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == persisted_id
        assert item["provider"] == "oci"
        assert Decimal(str(item["current_monthly_cost"])) == Decimal("44.55")
        assert Decimal(str(item["estimated_monthly_savings"])) == Decimal("44.55")
        assert item["currency"] == "BRL"
        assert item["provider_metadata"]["financial_value_populated"] is True

    second_time = START + timedelta(days=1)
    with Session(engine) as db:
        cloud_account = db.scalar(
            select(CloudAccount).where(CloudAccount.native_account_id == TENANCY_ID)
        )
        assert cloud_account is not None
        second_scan, second_run = _create_run(db, cloud_account, started_at=second_time)
        refreshed_finding = _block_volume_finding(size_in_gbs=600, vpus_per_gb=10)
        worker.persist_findings(
            db,
            second_scan,
            second_run,
            [refreshed_finding],
            [refreshed_finding.rule_key],
            observed_at=second_time,
        )
        db.commit()

        assert db.scalar(select(func.count()).select_from(Finding)) == 1
        assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 2
        refreshed = db.get(Finding, persisted_id)
        assert refreshed is not None
        assert refreshed.fingerprint == persisted_fingerprint
        assert refreshed.current_monthly_cost == Decimal("53.46")
        assert refreshed.estimated_monthly_savings == Decimal("53.46")
        assert refreshed.currency == "BRL"
        assert refreshed.provider_metadata["financial_value_populated"] is True

    engine.dispose()
