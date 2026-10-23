from datetime import UTC, datetime

from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import AwsAccount, CloudAccount
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services import rds_inventory
from app.services.rds_inventory import (
    collect_db_instances,
    collect_rds_inventory,
    days_until_expiration,
    normalize_rds_engine,
    parse_db_instance_class,
    reconcile_db_instances,
    reconcile_reserved_db_instances,
    reservation_expiration,
)


class FakePaginator:
    def __init__(self, pages=None, error=None):
        self.pages = pages or []
        self.error = error

    def paginate(self):
        if self.error:
            raise self.error
        yield from self.pages


class FakeRdsClient:
    def __init__(self, *, instances=None, reservations=None, instance_error=None):
        self.instances = instances or []
        self.reservations = reservations or []
        self.instance_error = instance_error

    def get_paginator(self, name):
        if name == "describe_db_instances":
            return FakePaginator(
                [
                    {"DBInstances": self.instances[:1]},
                    {"DBInstances": self.instances[1:]},
                ],
                error=self.instance_error,
            )
        if name == "describe_reserved_db_instances":
            return FakePaginator([{"ReservedDBInstances": self.reservations}])
        raise AssertionError(name)

    def list_tags_for_resource(self, *, ResourceName):
        return {"TagList": [{"Key": "Name", "Value": ResourceName.rsplit(":", 1)[-1]}]}


class FakeAwsSession:
    def __init__(self, clients):
        self.clients = clients

    def client(self, service_name, *, region_name=None, config=None):
        assert service_name == "rds"
        assert config is not None
        return self.clients[region_name]


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _instance(identifier="db-a", *, status="available", multi_az=True):
    return {
        "DBInstanceIdentifier": identifier,
        "DBInstanceArn": f"arn:aws:rds:sa-east-1:111111111111:db:{identifier}",
        "DBInstanceClass": "db.r6g.2xlarge",
        "Engine": "postgres",
        "EngineVersion": "16.3",
        "DBInstanceStatus": status,
        "MultiAZ": multi_az,
        "AvailabilityZone": "sa-east-1a",
        "SecondaryAvailabilityZone": "sa-east-1b",
        "LicenseModel": "postgresql-license",
        "StorageType": "gp3",
        "AllocatedStorage": 100,
        "Iops": 3000,
        "StorageThroughput": 125,
        "PubliclyAccessible": False,
        "DBSubnetGroup": {"VpcId": "vpc-123"},
        "InstanceCreateTime": datetime(2025, 1, 1, tzinfo=UTC),
    }


def _reservation(identifier="ri-a", *, count=2, multi_az=True):
    return {
        "ReservedDBInstanceId": identifier,
        "ReservedDBInstancesOfferingId": "offering-a",
        "DBInstanceClass": "db.r6g.2xlarge",
        "ProductDescription": "PostgreSQL",
        "DBInstanceCount": count,
        "MultiAZ": multi_az,
        "OfferingType": "Partial Upfront",
        "OfferingClass": "standard",
        "CurrencyCode": "USD",
        "FixedPrice": 123.45,
        "UsagePrice": 0.067,
        "RecurringCharges": [{"RecurringChargeAmount": 0.1, "RecurringChargeFrequency": "Hourly"}],
        "StartTime": datetime(2026, 1, 1, tzinfo=UTC),
        "Duration": 31536000,
        "State": "active",
        "LeaseId": "lease-a",
    }


def _cloud_account(db, account_id, regions):
    cloud = CloudAccount(
        provider="aws",
        native_account_id=account_id,
        name=f"AWS {account_id}",
        enabled=True,
    )
    cloud.aws_configuration = AwsAccount(
        name=cloud.name,
        aws_account_id=account_id,
        enabled=True,
        role_arn=f"arn:aws:iam::{account_id}:role/NuvemIQReadOnly",
        external_id=f"external-{account_id}",
        regions=regions,
    )
    db.add(cloud)
    db.commit()
    return cloud


def test_parse_db_instance_class():
    parsed = parse_db_instance_class("db.r6g.2xlarge")
    assert parsed.prefix == "db"
    assert parsed.family == "r6g"
    assert parsed.size == "2xlarge"
    assert parsed.full_class == "db.r6g.2xlarge"

    parsed = parse_db_instance_class("db.r6g.large")
    assert parsed.family == "r6g"
    assert parsed.size == "large"


def test_engine_normalization_is_conservative():
    assert normalize_rds_engine("postgres") == "postgres"
    assert normalize_rds_engine("PostgreSQL") == "postgres"
    assert normalize_rds_engine("Aurora MySQL") == "aurora-mysql"
    assert normalize_rds_engine("oracle-se2 (bring your own license)") == "oracle-se2"
    assert normalize_rds_engine("sqlserver-ex(li)") == "sqlserver-ex"
    assert normalize_rds_engine("oracle-se") == "oracle-se"
    assert normalize_rds_engine("oracle-se2") != normalize_rds_engine("oracle-se")


def test_reservation_expiration_and_days_until_expiration():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    expiration = reservation_expiration(start, 31536000)
    assert expiration == datetime(2027, 1, 1, tzinfo=UTC)
    assert (
        days_until_expiration(
            expiration,
            now=datetime(2026, 12, 2, tzinfo=UTC),
        )
        == 30
    )


def test_db_instance_collection_uses_pagination_and_tags():
    client = FakeRdsClient(instances=[_instance("db-a"), _instance("db-b")])
    items = collect_db_instances(client)
    assert [item["DBInstanceIdentifier"] for item in items] == ["db-a", "db-b"]
    assert items[0]["_DeepOpsTags"]["Name"] == "db-a"


def test_reconcile_instances_is_idempotent_and_marks_disappeared():
    with _db() as db:
        cloud = _cloud_account(db, "111111111111", ["sa-east-1"])
        first = reconcile_db_instances(
            db,
            cloud_account_id=cloud.id,
            account_id=cloud.native_account_id,
            region="sa-east-1",
            items=[_instance()],
        )
        db.commit()
        assert first == {"found": 1, "created": 1, "updated": 0, "marked_inactive": 0}

        second = reconcile_db_instances(
            db,
            cloud_account_id=cloud.id,
            account_id=cloud.native_account_id,
            region="sa-east-1",
            items=[_instance(status="modifying")],
        )
        db.commit()
        assert second["created"] == 0
        assert second["updated"] == 1
        assert db.query(AwsRdsInstance).count() == 1
        assert db.query(AwsRdsInstance).one().status == "modifying"

        third = reconcile_db_instances(
            db,
            cloud_account_id=cloud.id,
            account_id=cloud.native_account_id,
            region="sa-east-1",
            items=[],
        )
        db.commit()
        assert third["marked_inactive"] == 1
        assert db.query(AwsRdsInstance).one().is_active is False


def test_reconcile_reservations_preserves_count_multiaz_money_and_expiration():
    with _db() as db:
        cloud = _cloud_account(db, "111111111111", ["sa-east-1"])
        counts = reconcile_reserved_db_instances(
            db,
            cloud_account_id=cloud.id,
            account_id=cloud.native_account_id,
            region="sa-east-1",
            items=[_reservation()],
        )
        db.commit()
        assert counts["created"] == 1
        row = db.query(AwsRdsReservedInstance).one()
        assert row.instance_count == 2
        assert row.multi_az is True
        assert row.fixed_price == "123.45"
        assert row.usage_price == "0.067"
        assert row.expiration_at.replace(tzinfo=UTC) == datetime(2027, 1, 1, tzinfo=UTC)
        assert row.recurring_charges[0]["RecurringChargeFrequency"] == "Hourly"


def test_collect_inventory_isolates_access_denied_by_account_and_region(monkeypatch):
    with _db() as db:
        first = _cloud_account(db, "111111111111", ["sa-east-1", "us-east-1"])
        second = _cloud_account(db, "222222222222", ["sa-east-1"])

        denied = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "DescribeDBInstances",
        )
        sessions = {
            first.id: FakeAwsSession(
                {
                    "sa-east-1": FakeRdsClient(
                        instances=[_instance("db-a")],
                        reservations=[_reservation("ri-a")],
                    ),
                    "us-east-1": FakeRdsClient(
                        instances=[_instance("db-b")],
                        reservations=[],
                    ),
                }
            ),
            second.id: FakeAwsSession(
                {
                    "sa-east-1": FakeRdsClient(
                        reservations=[_reservation("ri-b")],
                        instance_error=denied,
                    )
                }
            ),
        }

        def assume(account):
            return sessions[account.cloud_account_id]

        monkeypatch.setattr(rds_inventory, "assume_account_session", assume)
        result = collect_rds_inventory(db)

        assert result["accounts_processed"] == 2
        assert result["regions_processed"] == 3
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error"] == "AccessDenied"
        assert db.query(AwsRdsInstance).count() == 2
        assert db.query(AwsRdsReservedInstance).count() == 2


def test_optional_instance_fields_can_be_absent():
    with _db() as db:
        cloud = _cloud_account(db, "111111111111", ["sa-east-1"])
        minimal = {
            "DBInstanceIdentifier": "minimal",
            "DBInstanceArn": "arn:aws:rds:sa-east-1:111111111111:db:minimal",
            "DBInstanceClass": "db.t4g.micro",
            "Engine": "mysql",
            "DBInstanceStatus": "available",
        }
        reconcile_db_instances(
            db,
            cloud_account_id=cloud.id,
            account_id=cloud.native_account_id,
            region="sa-east-1",
            items=[minimal],
        )
        db.commit()
        row = db.query(AwsRdsInstance).one()
        assert row.multi_az is False
        assert row.license_model is None
        assert row.tags == {}
        assert row.processor_features == []
