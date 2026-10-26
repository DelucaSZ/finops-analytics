from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import AwsAccount
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.rds_coverage import (
    RdsInstanceReservationCoverage,
    RdsReservationCoverageRun,
    RdsReservationUtilization,
)
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_reservation_opportunities import (
    RDS_RESERVATION_EXPIRING,
    RDS_RESERVATION_PARTIAL_COVERAGE,
    RDS_RESERVATION_UNCOVERED,
    RDS_RESERVATION_UNUSED_CAPACITY,
    generate_rds_reservation_opportunities,
    rds_reservation_opportunity_summary,
)

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
ACCOUNT = "111111111111"
REGION = "sa-east-1"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        account = AwsAccount(
            id=1,
            name="Production",
            aws_account_id=ACCOUNT,
            role_arn="arn:aws:iam::111111111111:role/deepops",
            external_id="test",
        )
        session.add(account)
        session.commit()
        yield session
    engine.dispose()


def _instance(
    db: Session,
    identifier: str = "db-prod-postgres-01",
    *,
    collected_at: datetime = NOW,
) -> AwsRdsInstance:
    account = db.get(AwsAccount, 1)
    row = AwsRdsInstance(
        cloud_account_id=account.cloud_account_id,
        account_id=ACCOUNT,
        region=REGION,
        db_instance_identifier=identifier,
        db_instance_arn=f"arn:aws:rds:{REGION}:{ACCOUNT}:db:{identifier}",
        db_instance_class="db.r7g.xlarge",
        class_prefix="db",
        instance_family="r7g",
        instance_size="xlarge",
        engine="postgres",
        engine_normalized="postgres",
        engine_version="16.1",
        license_model="postgresql-license",
        status="available",
        coverage_eligible=True,
        multi_az=False,
        collected_at=collected_at,
        last_seen_at=collected_at,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _reservation(
    db: Session,
    reservation_id: str = "ri-rds-01",
    *,
    expires_in_days: int = 10,
    collected_at: datetime = NOW,
) -> AwsRdsReservedInstance:
    account = db.get(AwsAccount, 1)
    row = AwsRdsReservedInstance(
        cloud_account_id=account.cloud_account_id,
        account_id=ACCOUNT,
        region=REGION,
        reserved_db_instance_id=reservation_id,
        db_instance_class="db.r7g.xlarge",
        class_prefix="db",
        instance_family="r7g",
        instance_size="xlarge",
        product_description="postgres",
        engine_normalized="postgres",
        instance_count=2,
        multi_az=False,
        state="active",
        start_time=NOW - timedelta(days=100),
        duration_seconds=365 * 86400,
        expiration_at=NOW + timedelta(days=expires_in_days),
        collected_at=collected_at,
        last_seen_at=collected_at,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _run(db: Session, *, at: datetime = NOW) -> RdsReservationCoverageRun:
    run = RdsReservationCoverageRun(
        started_at=at,
        completed_at=at,
        inventory_snapshot_at=at,
        status="COMPLETED",
        reconciliation_status="NOT_AVAILABLE",
        billing_validation_status="NOT_AVAILABLE",
    )
    db.add(run)
    db.flush()
    return run


def _coverage(
    db: Session,
    run: RdsReservationCoverageRun,
    instance: AwsRdsInstance,
    *,
    status: str,
    required: str,
    covered: str,
) -> RdsInstanceReservationCoverage:
    required_d = Decimal(required)
    covered_d = Decimal(covered)
    uncovered_d = max(Decimal("0"), required_d - covered_d)
    pct = (
        Decimal("0")
        if required_d == 0
        else covered_d / required_d * Decimal("100")
    )
    row = RdsInstanceReservationCoverage(
        coverage_run_id=run.id,
        rds_instance_id=instance.id,
        account_id=instance.account_id,
        region=instance.region,
        required_units=required_d,
        covered_units=covered_d,
        uncovered_units=uncovered_d,
        coverage_percentage=pct,
        coverage_status=status,
        coverage_scope="SAME_ACCOUNT",
        calculation_method="NORMALIZED_UNITS",
        explanation={"code": status},
    )
    db.add(row)
    db.flush()
    return row


def _utilization(
    db: Session,
    run: RdsReservationCoverageRun,
    reservation: AwsRdsReservedInstance,
    *,
    total: str,
    allocated: str,
) -> RdsReservationUtilization:
    total_d = Decimal(total)
    allocated_d = Decimal(allocated)
    unused_d = max(Decimal("0"), total_d - allocated_d)
    pct = (
        Decimal("0")
        if total_d == 0
        else allocated_d / total_d * Decimal("100")
    )
    row = RdsReservationUtilization(
        coverage_run_id=run.id,
        reservation_id=reservation.id,
        total_units=total_d,
        allocated_units=allocated_d,
        unused_units=unused_d,
        utilization_percentage=pct,
    )
    db.add(row)
    db.flush()
    return row


def _finding(db: Session, rule: str, resource_id: str) -> Finding | None:
    return (
        db.query(Finding)
        .filter(Finding.rule_key == rule, Finding.resource_id == resource_id)
        .one_or_none()
    )


def test_uncovered_is_idempotent_and_preserves_first_seen(db: Session) -> None:
    instance = _instance(db)
    run = _run(db)
    _coverage(db, run, instance, status="UNCOVERED", required="8", covered="0")
    db.commit()

    first = generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()
    finding = _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier)
    assert first.created == 1
    assert finding is not None
    assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
    assert finding.provider_metadata["coverage_percentage"] == 0.0
    assert finding.provider_metadata["savings_status"] == "not_calculated"
    first_seen = finding.first_seen_at

    second = generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()
    assert second.created == 0
    assert (
        db.query(Finding)
        .filter(
            Finding.rule_key == RDS_RESERVATION_UNCOVERED,
            Finding.resource_id == instance.db_instance_identifier,
        )
        .count()
        == 1
    )
    assert _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier).first_seen_at == first_seen


def test_transition_uncovered_partial_full_has_only_current_active_finding(db: Session) -> None:
    instance = _instance(db)

    run1 = _run(db, at=NOW)
    _coverage(db, run1, instance, status="UNCOVERED", required="8", covered="0")
    db.commit()
    generate_rds_reservation_opportunities(db, coverage_run_id=run1.id, now=NOW)
    db.commit()

    run2 = _run(db, at=NOW + timedelta(hours=1))
    _coverage(db, run2, instance, status="PARTIAL", required="8", covered="4")
    db.commit()
    generate_rds_reservation_opportunities(
        db, coverage_run_id=run2.id, now=NOW + timedelta(hours=1)
    )
    db.commit()

    uncovered = _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier)
    partial = _finding(
        db, RDS_RESERVATION_PARTIAL_COVERAGE, instance.db_instance_identifier
    )
    assert uncovered.presence_status == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
    assert partial.presence_status == OpportunityPresenceStatus.ACTIVE.value
    assert partial.provider_metadata["coverage_percentage"] == 50.0

    run3 = _run(db, at=NOW + timedelta(hours=2))
    _coverage(db, run3, instance, status="FULL", required="8", covered="8")
    db.commit()
    generate_rds_reservation_opportunities(
        db, coverage_run_id=run3.id, now=NOW + timedelta(hours=2)
    )
    db.commit()

    assert (
        _finding(db, RDS_RESERVATION_PARTIAL_COVERAGE, instance.db_instance_identifier).presence_status
        == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
    )
    active = (
        db.query(Finding)
        .filter(
            Finding.resource_id == instance.db_instance_identifier,
            Finding.rule_key.in_(
                [RDS_RESERVATION_UNCOVERED, RDS_RESERVATION_PARTIAL_COVERAGE]
            ),
            Finding.presence_status == OpportunityPresenceStatus.ACTIVE.value,
        )
        .count()
    )
    assert active == 0


def test_unknown_never_becomes_uncovered(db: Session) -> None:
    instance = _instance(db, "db-unknown")
    run = _run(db)
    _coverage(db, run, instance, status="UNKNOWN", required="0", covered="0")
    db.commit()

    result = generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()

    assert result.unknown_skipped == 1
    assert _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier) is None


def test_stale_inventory_does_not_create_new_opportunity(db: Session) -> None:
    instance = _instance(db, "db-stale", collected_at=NOW - timedelta(hours=48))
    run = _run(db)
    _coverage(db, run, instance, status="UNCOVERED", required="8", covered="0")
    db.commit()

    result = generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()

    assert result.stale_skipped == 1
    assert _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier) is None


def test_unused_capacity_resolves_when_fully_allocated(db: Session) -> None:
    reservation = _reservation(db, expires_in_days=90)
    run1 = _run(db)
    _utilization(db, run1, reservation, total="16", allocated="8")
    db.commit()
    generate_rds_reservation_opportunities(db, coverage_run_id=run1.id, now=NOW)
    db.commit()

    finding = _finding(db, RDS_RESERVATION_UNUSED_CAPACITY, reservation.reserved_db_instance_id)
    assert finding is not None
    assert finding.provider_metadata["unused_units"] == 8.0
    assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value

    run2 = _run(db, at=NOW + timedelta(hours=1))
    _utilization(db, run2, reservation, total="16", allocated="16")
    db.commit()
    result = generate_rds_reservation_opportunities(
        db, coverage_run_id=run2.id, now=NOW + timedelta(hours=1)
    )
    db.commit()

    assert result.resolved >= 1
    assert (
        _finding(db, RDS_RESERVATION_UNUSED_CAPACITY, reservation.reserved_db_instance_id).presence_status
        == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
    )


@pytest.mark.parametrize(
    ("days", "expected", "band", "severity"),
    [
        (31, False, None, None),
        (30, True, "medium", "medium"),
        (16, True, "medium", "medium"),
        (15, True, "high", "high"),
        (8, True, "high", "high"),
        (7, True, "critical", "high"),
        (1, True, "critical", "high"),
        (0, True, "critical", "high"),
        (-1, False, None, None),
    ],
)
def test_expiration_thresholds(
    db: Session,
    days: int,
    expected: bool,
    band: str | None,
    severity: str | None,
) -> None:
    reservation = _reservation(db, f"ri-{days}", expires_in_days=days)
    run = _run(db)
    _utilization(db, run, reservation, total="16", allocated="16")
    db.commit()

    generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()
    finding = _finding(db, RDS_RESERVATION_EXPIRING, reservation.reserved_db_instance_id)

    assert (finding is not None and finding.presence_status == "active") is expected
    if expected:
        assert finding.provider_metadata["expiration_band"] == band
        assert finding.severity == severity


def test_expiring_recommendation_depends_on_current_utilization(db: Session) -> None:
    used = _reservation(db, "ri-used", expires_in_days=10)
    unused = _reservation(db, "ri-unused", expires_in_days=10)
    run = _run(db)
    _utilization(db, run, used, total="16", allocated="16")
    _utilization(db, run, unused, total="16", allocated="0")
    db.commit()

    generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()

    used_finding = _finding(db, RDS_RESERVATION_EXPIRING, "ri-used")
    unused_finding = _finding(db, RDS_RESERVATION_EXPIRING, "ri-unused")
    assert "renovação ou substituição" in used_finding.provider_metadata["recommended_action"]
    assert "antes de renovar" in unused_finding.provider_metadata["recommended_action"]


def test_summary_exposes_coverage_reservation_and_expiration_totals(db: Session) -> None:
    instance = _instance(db)
    reservation = _reservation(db, expires_in_days=10)
    run = _run(db)
    _coverage(db, run, instance, status="PARTIAL", required="16", covered="8")
    _utilization(db, run, reservation, total="16", allocated="8")
    db.commit()
    generate_rds_reservation_opportunities(db, coverage_run_id=run.id, now=NOW)
    db.commit()

    summary = rds_reservation_opportunity_summary(
        db, coverage_run_id=run.id, now=NOW
    )
    assert summary["rds"]["partially_covered"] == 1
    assert summary["coverage"]["coverage_percentage"] == 50.0
    assert summary["reservations"]["unused_units"] == 8.0
    assert summary["expirations"]["next_15_days"] == 1
    assert summary["opportunities"]["partial"] == 1
    assert summary["opportunities"]["unused_capacity"] == 1
    assert summary["opportunities"]["expiring"] == 1


def test_rejected_finding_is_not_reopened_as_user_status(db: Session) -> None:
    instance = _instance(db)
    run1 = _run(db)
    _coverage(db, run1, instance, status="UNCOVERED", required="8", covered="0")
    db.commit()
    generate_rds_reservation_opportunities(db, coverage_run_id=run1.id, now=NOW)
    db.commit()

    finding = _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier)
    finding.status = "rejected"
    db.commit()

    run2 = _run(db, at=NOW + timedelta(hours=1))
    _coverage(db, run2, instance, status="UNCOVERED", required="8", covered="0")
    db.commit()
    generate_rds_reservation_opportunities(
        db, coverage_run_id=run2.id, now=NOW + timedelta(hours=1)
    )
    db.commit()

    refreshed = _finding(db, RDS_RESERVATION_UNCOVERED, instance.db_instance_identifier)
    assert refreshed.status == "rejected"
    assert refreshed.presence_status == OpportunityPresenceStatus.ACTIVE.value
