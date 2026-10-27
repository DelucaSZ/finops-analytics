from datetime import UTC, datetime, timedelta

import boto3.session
from oci.base_client import BaseClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.inventory import InventoryResource
from app.services import oci_inventory_adapter
from app.services.aws_inventory_discovery import AwsInventoryDiscoveryService
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _seed_inventory(engine):
    observed = datetime(2026, 10, 27, 18, tzinfo=UTC)
    with Session(engine) as db:
        aws = db.scalar(select(CloudAccount).where(CloudAccount.provider == "aws"))
        oci_account = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..inventoryquery",
            name="OCI Production",
        )
        db.add(oci_account)
        db.flush()

        rows = [
            InventoryResource(
                provider="aws",
                cloud_account_id=aws.id,
                native_account_id=aws.native_account_id,
                resource_id="i-api-001",
                resource_type="compute_instance",
                native_resource_type="AWS::EC2::Instance",
                service="EC2",
                name="API Production",
                region="us-east-1",
                availability_zone="us-east-1a",
                lifecycle_status="running",
                native_status="running",
                tags={"Environment": "prod"},
                attributes={"instance_type": "m6i.large"},
                presence_status="active",
                first_seen_at=observed - timedelta(days=10),
                last_seen_at=observed,
            ),
            InventoryResource(
                provider="aws",
                cloud_account_id=aws.id,
                native_account_id=aws.native_account_id,
                resource_id="i-api-002",
                resource_type="compute_instance",
                native_resource_type="AWS::EC2::Instance",
                service="EC2",
                name="api worker",
                region="us-east-1",
                availability_zone="us-east-1b",
                lifecycle_status="running",
                native_status="running",
                tags={},
                attributes={"instance_type": "m6i.xlarge"},
                presence_status="active",
                first_seen_at=observed - timedelta(days=5),
                last_seen_at=observed,
            ),
            InventoryResource(
                provider="aws",
                cloud_account_id=aws.id,
                native_account_id=aws.native_account_id,
                resource_id="vol-old-001",
                resource_type="block_volume",
                native_resource_type="AWS::EC2::Volume",
                service="EC2",
                name="Old volume",
                region="us-west-2",
                lifecycle_status="available",
                native_status="available",
                tags={},
                attributes={"size_gb": 100},
                presence_status="missing",
                first_seen_at=observed - timedelta(days=30),
                last_seen_at=observed - timedelta(days=2),
            ),
            InventoryResource(
                provider="aws",
                cloud_account_id=aws.id,
                native_account_id=aws.native_account_id,
                resource_id="db-prod-001",
                resource_type="relational_database",
                native_resource_type="AWS::RDS::DBInstance",
                service="RDS",
                name="Orders DB",
                region="us-west-2",
                lifecycle_status="available",
                native_status="available",
                tags={},
                attributes={"engine": "postgres"},
                presence_status="active",
                first_seen_at=observed - timedelta(days=20),
                last_seen_at=observed - timedelta(hours=1),
            ),
            InventoryResource(
                provider="aws",
                cloud_account_id=aws.id,
                native_account_id=aws.native_account_id,
                resource_id="eipalloc-001",
                resource_type="public_ip",
                native_resource_type="AWS::EC2::EIP",
                service="EC2",
                name=None,
                region="us-east-1",
                lifecycle_status="available",
                native_status="available",
                tags={},
                attributes={},
                presence_status="active",
                first_seen_at=observed - timedelta(days=2),
                last_seen_at=observed - timedelta(minutes=5),
            ),
            InventoryResource(
                provider="oci",
                cloud_account_id=oci_account.id,
                native_account_id=oci_account.native_account_id,
                resource_id="ocid1.instance.oc1.sa-saopaulo-1.compute001",
                resource_type="compute_instance",
                native_resource_type="Instance",
                service="Compute",
                name="OCI API",
                region="sa-saopaulo-1",
                availability_zone="AD-1",
                lifecycle_status="running",
                native_status="RUNNING",
                tags={"freeform": {"Environment": "prod"}},
                attributes={"shape": "VM.Standard.E4.Flex"},
                presence_status="active",
                first_seen_at=observed - timedelta(days=3),
                last_seen_at=observed - timedelta(minutes=2),
            ),
            InventoryResource(
                provider="oci",
                cloud_account_id=oci_account.id,
                native_account_id=oci_account.native_account_id,
                resource_id="ocid1.bootvolume.oc1.sa-saopaulo-1.boot001",
                resource_type="boot_volume",
                native_resource_type="BootVolume",
                service="Block Storage",
                name="Boot volume",
                region="sa-saopaulo-1",
                lifecycle_status="available",
                native_status="AVAILABLE",
                tags={},
                attributes={"size_gb": 50},
                presence_status="active",
                first_seen_at=observed - timedelta(days=3),
                last_seen_at=observed - timedelta(minutes=3),
            ),
        ]
        db.add_all(rows)
        db.commit()
        return aws.id, oci_account.id


def test_inventory_requires_authentication_and_all_roles_can_read(auth_env):
    client, engine, tokens, _ = auth_env
    _seed_inventory(engine)
    assert client.get("/api/v1/inventory/resources").status_code == 401
    for role in ("admin", "operator", "viewer"):
        response = client.get("/api/v1/inventory/resources", headers=headers(tokens, role))
        assert response.status_code == 200
        assert response.json()["total"] == 7


def test_inventory_list_filters_search_pagination_and_stable_sort(auth_env):
    client, engine, tokens, _ = auth_env
    aws_id, _ = _seed_inventory(engine)
    auth = headers(tokens, "viewer")

    response = client.get(
        "/api/v1/inventory/resources",
        headers=auth,
        params={
            "provider": "AWS",
            "account_id": aws_id,
            "region": "us-east-1",
            "resource_type": "compute_instance",
            "lifecycle_status": "running",
            "presence_status": "active",
            "service": "EC2",
            "search": "  API  ",
            "sort": "last_seen_at",
            "direction": "desc",
            "page": 1,
            "page_size": 1,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["resource_id"] == "i-api-002"
    assert body["items"][0]["account_name"] == "Account"

    page2 = client.get(
        "/api/v1/inventory/resources",
        headers=auth,
        params={"provider": "aws", "search": "api", "page": 2, "page_size": 1},
    ).json()
    assert page2["total"] >= 2
    assert page2["page"] == 2


def test_inventory_filters_cover_aws_oci_missing_types_and_native_account_search(auth_env):
    client, engine, tokens, _ = auth_env
    _seed_inventory(engine)
    auth = headers(tokens)

    aws = client.get(
        "/api/v1/inventory/resources", headers=auth, params={"provider": "aws"}
    ).json()
    assert aws["total"] == 5
    assert {item["provider"] for item in aws["items"]} == {"aws"}

    oci_rows = client.get(
        "/api/v1/inventory/resources",
        headers=auth,
        params={"provider": "oci", "region": "sa-saopaulo-1"},
    ).json()
    assert oci_rows["total"] == 2
    assert {item["resource_type"] for item in oci_rows["items"]} == {
        "compute_instance",
        "boot_volume",
    }

    absent_account = client.get(
        "/api/v1/inventory/resources", headers=auth, params={"account_id": 999999}
    ).json()
    assert absent_account["items"] == []
    assert absent_account["total"] == 0

    missing = client.get(
        "/api/v1/inventory/resources", headers=auth, params={"presence_status": "missing"}
    ).json()
    assert missing["total"] == 1
    assert missing["items"][0]["resource_id"] == "vol-old-001"

    native = client.get(
        "/api/v1/inventory/resources",
        headers=auth,
        params={"search": "TENANCY.OC1..INVENTORYQUERY"},
    ).json()
    assert native["total"] == 2


def test_inventory_validation_sorting_and_bounds(auth_env):
    client, engine, tokens, _ = auth_env
    _seed_inventory(engine)
    auth = headers(tokens)

    assert client.get(
        "/api/v1/inventory/resources", headers=auth, params={"provider": "nope"}
    ).status_code == 422
    assert client.get(
        "/api/v1/inventory/resources", headers=auth, params={"sort": "drop table"}
    ).status_code == 422
    assert client.get(
        "/api/v1/inventory/resources", headers=auth, params={"direction": "sideways"}
    ).status_code == 422
    assert client.get(
        "/api/v1/inventory/resources", headers=auth, params={"page_size": 101}
    ).status_code == 422
    assert client.get(
        "/api/v1/inventory/resources", headers=auth, params={"search": "x" * 257}
    ).status_code == 422

    for sort_field in ("name", "last_seen_at", "region", "resource_type"):
        for direction in ("asc", "desc"):
            sorted_response = client.get(
                "/api/v1/inventory/resources",
                headers=auth,
                params={"sort": sort_field, "direction": direction, "page_size": 100},
            )
            assert sorted_response.status_code == 200, (
                sort_field,
                direction,
                sorted_response.text,
            )
            assert len(sorted_response.json()["items"]) == 7

    empty = client.get(
        "/api/v1/inventory/resources", headers=auth, params={"provider": "gcp"}
    )
    assert empty.status_code == 200
    assert empty.json() == {
        "items": [],
        "page": 1,
        "page_size": 50,
        "total": 0,
        "total_pages": 0,
    }

    for term in ("does-not-exist", "%", "_", "' OR 1=1 --"):
        searched = client.get(
            "/api/v1/inventory/resources", headers=auth, params={"search": term}
        )
        assert searched.status_code == 200
        if term == "does-not-exist":
            assert searched.json()["total"] == 0

    beyond = client.get(
        "/api/v1/inventory/resources", headers=auth, params={"page": 99, "page_size": 2}
    ).json()
    assert beyond["items"] == []
    assert beyond["total"] == 7
    assert beyond["total_pages"] == 4


def test_inventory_options_are_real_deduplicated_and_cascading(auth_env):
    client, engine, tokens, _ = auth_env
    aws_id, _ = _seed_inventory(engine)
    auth = headers(tokens)

    all_options = client.get("/api/v1/inventory/options", headers=auth)
    assert all_options.status_code == 200
    body = all_options.json()
    assert body["providers"] == ["aws", "oci"]
    assert {item["provider"] for item in body["accounts"]} == {"aws", "oci"}
    assert "sa-saopaulo-1" in body["regions"]
    assert "us-east-1" in body["regions"]
    assert set(body["presence_statuses"]) == {"active", "missing"}

    aws_options = client.get(
        "/api/v1/inventory/options",
        headers=auth,
        params={"provider": "aws", "account_id": aws_id},
    ).json()
    assert aws_options["providers"] == ["aws"]
    assert {item["provider"] for item in aws_options["accounts"]} == {"aws"}
    assert "sa-saopaulo-1" not in aws_options["regions"]
    assert "Compute" not in aws_options["services"]


def test_inventory_detail_returns_public_contract_and_hides_absence(auth_env):
    client, engine, tokens, _ = auth_env
    _seed_inventory(engine)
    auth = headers(tokens, "viewer")
    listing = client.get(
        "/api/v1/inventory/resources",
        headers=auth,
        params={"search": "i-api-001"},
    ).json()
    resource_id = listing["items"][0]["id"]

    detail = client.get(f"/api/v1/inventory/resources/{resource_id}", headers=auth)
    assert detail.status_code == 200
    body = detail.json()
    assert body["resource_id"] == "i-api-001"
    assert body["tags"] == {"Environment": "prod"}
    assert body["attributes"] == {"instance_type": "m6i.large"}
    assert "first_seen_collection_run_id" in body
    assert client.get("/api/v1/inventory/resources/999999", headers=auth).status_code == 404


def test_inventory_http_queries_do_not_touch_cloud_or_discovery(auth_env, monkeypatch):
    client, engine, tokens, _ = auth_env
    _seed_inventory(engine)
    auth = headers(tokens)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Inventory Query API must not execute cloud/discovery code")

    monkeypatch.setattr(AwsInventoryDiscoveryService, "discover", forbidden)
    monkeypatch.setattr(oci_inventory_adapter, "adapt_oci_inventory", forbidden)
    monkeypatch.setattr(boto3.session.Session, "client", forbidden)
    monkeypatch.setattr(BaseClient, "call_api", forbidden)

    listing = client.get("/api/v1/inventory/resources", headers=auth)
    assert listing.status_code == 200
    resource_id = listing.json()["items"][0]["id"]
    assert client.get("/api/v1/inventory/options", headers=auth).status_code == 200
    assert client.get(f"/api/v1/inventory/resources/{resource_id}", headers=auth).status_code == 200


def test_inventory_listing_has_no_account_name_n_plus_one(auth_env):
    client, engine, tokens, _ = auth_env
    _seed_inventory(engine)
    auth = headers(tokens)
    with Session(engine) as db:
        aws = db.scalar(select(CloudAccount).where(CloudAccount.provider == "aws"))
        observed = datetime(2026, 10, 27, 19, tzinfo=UTC)
        for index in range(50):
            db.add(
                InventoryResource(
                    provider="aws",
                    cloud_account_id=aws.id,
                    native_account_id=aws.native_account_id,
                    resource_id=f"i-bulk-{index:03d}",
                    resource_type="compute_instance",
                    service="EC2",
                    name=f"bulk-{index:03d}",
                    region="us-east-1",
                    lifecycle_status="running",
                    tags={},
                    attributes={},
                    presence_status="active",
                    first_seen_at=observed,
                    last_seen_at=observed,
                )
            )
        db.commit()

    inventory_selects = []

    @event.listens_for(engine, "before_cursor_execute")
    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = statement.lower().lstrip()
        if normalized.startswith("select") and (
            "inventory_resources" in normalized or "cloud_accounts" in normalized
        ):
            inventory_selects.append(statement)

    response = client.get(
        "/api/v1/inventory/resources",
        headers=auth,
        params={"provider": "aws", "page_size": 50},
    )
    event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 50
    assert len(inventory_selects) <= 3
