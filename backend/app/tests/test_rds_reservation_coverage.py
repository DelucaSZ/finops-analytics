from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_reservation_engine import RdsReservationCoverageEngine
from app.services.rds_reservation_rules import (
    BillingScopeContext,
    COVERAGE_FULL,
    COVERAGE_PARTIAL,
    COVERAGE_UNCOVERED,
    COVERAGE_UNKNOWN,
    CROSS_ACCOUNT_VERIFIED,
    NORMALIZED_UNITS,
    RdsReservationMatcher,
    instance_required_units,
    normalized_units_for_size,
    reservation_total_units,
    supports_size_flexibility,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def _instance(
    identifier: str,
    instance_class: str,
    *,
    row_id: int = 1,
    account: str = "111111111111",
    region: str = "sa-east-1",
    engine: str = "postgres",
    license_model: str | None = "postgresql-license",
    multi_az: bool = False,
    topology: str | None = None,
    storage: str | None = None,
    status: str = "available",
) -> AwsRdsInstance:
    _, family, size = instance_class.split(".", 2)
    return AwsRdsInstance(
        id=row_id,
        cloud_account_id=1,
        account_id=account,
        region=region,
        db_instance_identifier=identifier,
        db_instance_arn=f"arn:aws:rds:{region}:{account}:db:{identifier}",
        db_instance_class=instance_class,
        class_prefix="db",
        instance_family=family,
        instance_size=size,
        engine=engine,
        engine_normalized=engine,
        engine_version="16.1",
        license_model=license_model,
        status=status,
        coverage_eligible=True,
        multi_az=multi_az,
        deployment_topology=topology,
        cluster_storage_type=storage,
        is_active=True,
    )


def _reservation(
    reservation_id: str,
    instance_class: str,
    *,
    row_id: int = 1,
    account: str = "111111111111",
    region: str = "sa-east-1",
    engine: str = "postgres",
    product_description: str | None = None,
    count: int = 1,
    multi_az: bool = False,
    state: str = "active",
) -> AwsRdsReservedInstance:
    _, family, size = instance_class.split(".", 2)
    return AwsRdsReservedInstance(
        id=row_id,
        cloud_account_id=1,
        account_id=account,
        region=region,
        reserved_db_instance_id=reservation_id,
        db_instance_class=instance_class,
        class_prefix="db",
        instance_family=family,
        instance_size=size,
        product_description=product_description or engine,
        engine_normalized=engine,
        instance_count=count,
        multi_az=multi_az,
        state=state,
        start_time=NOW - timedelta(days=100),
        duration_seconds=365 * 86400,
        expiration_at=NOW + timedelta(days=265),
        is_active=True,
    )


@pytest.mark.parametrize(
    ("size", "units"),
    [
        ("micro", "0.5"),
        ("small", "1"),
        ("medium", "2"),
        ("large", "4"),
        ("xlarge", "8"),
        ("2xlarge", "16"),
        ("4xlarge", "32"),
        ("6xlarge", "48"),
        ("8xlarge", "64"),
        ("10xlarge", "80"),
        ("12xlarge", "96"),
        ("16xlarge", "128"),
        ("24xlarge", "192"),
        ("32xlarge", "256"),
    ],
)
def test_normalized_units_table(size: str, units: str) -> None:
    assert NORMALIZED_UNITS[size] == Decimal(units)
    assert normalized_units_for_size(size) == Decimal(units)


def test_unknown_size_is_not_guessed() -> None:
    with pytest.raises(ValueError, match="unsupported DB instance size"):
        normalized_units_for_size("48xlarge")


def test_size_flexibility_scenario_a_large_reservation_covers_two_small() -> None:
    reservation = _reservation("ri-1", "db.r6g.large")
    instances = [
        _instance("db-a", "db.r6g.small", row_id=1),
        _instance("db-b", "db.r6g.small", row_id=2),
    ]
    result = RdsReservationCoverageEngine().analyze(instances, [reservation], at=NOW)
    assert [item.coverage_status for item in result.instances] == [COVERAGE_FULL, COVERAGE_FULL]
    assert sum((item.covered_units for item in result.instances), Decimal("0")) == Decimal("2")


def test_size_flexibility_scenario_b_large_reservation_partially_covers_xlarge() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [_instance("db-a", "db.r6g.xlarge")],
        [_reservation("ri-1", "db.r6g.large")],
        at=NOW,
    )
    coverage = result.instances[0]
    assert coverage.required_units == Decimal("8")
    assert coverage.covered_units == Decimal("4")
    assert coverage.coverage_percentage == Decimal("50")
    assert coverage.coverage_status == COVERAGE_PARTIAL


def test_size_flexibility_scenario_c_xlarge_reservation_covers_two_large() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [
            _instance("db-a", "db.r6g.large", row_id=1),
            _instance("db-b", "db.r6g.large", row_id=2),
        ],
        [_reservation("ri-1", "db.r6g.xlarge")],
        at=NOW,
    )
    assert all(item.coverage_status == COVERAGE_FULL for item in result.instances)
    assert result.reservations[0].unused_units == Decimal("0")


def test_family_mismatch_does_not_cover() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [_instance("db-a", "db.r6id.large")],
        [_reservation("ri-1", "db.r6i.large")],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_UNCOVERED


def test_engine_mismatch_does_not_cover() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [_instance("db-a", "db.r6g.large", engine="mysql", license_model="general-public-license")],
        [_reservation("ri-1", "db.r6g.large", engine="postgres")],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_UNCOVERED


def test_sql_server_does_not_use_size_flexibility() -> None:
    assert not supports_size_flexibility("sqlserver-se", "license-included")
    result = RdsReservationCoverageEngine().analyze(
        [
            _instance(
                "sql-a",
                "db.r6i.xlarge",
                engine="sqlserver-se",
                license_model="license-included",
            )
        ],
        [
            _reservation(
                "ri-sql",
                "db.r6i.large",
                engine="sqlserver-se",
                product_description="sqlserver-se (license-included)",
            )
        ],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_UNCOVERED


def test_sql_server_edition_mismatch_does_not_cover() -> None:
    matcher = RdsReservationMatcher()
    decision = matcher.match(
        _reservation(
            "ri-sql",
            "db.r6i.large",
            engine="sqlserver-se",
            product_description="sqlserver-se (license-included)",
        ),
        _instance(
            "sql-a",
            "db.r6i.large",
            engine="sqlserver-ee",
            license_model="license-included",
        ),
        at=NOW,
    )
    assert not decision.compatible
    assert decision.reason == "ENGINE_MISMATCH"


def test_oracle_byol_is_flexible_but_license_included_is_exact() -> None:
    assert supports_size_flexibility("oracle-ee", "bring-your-own-license")
    assert not supports_size_flexibility("oracle-ee", "license-included")

    byol = RdsReservationCoverageEngine().analyze(
        [
            _instance(
                "ora-a",
                "db.r6i.xlarge",
                engine="oracle-ee",
                license_model="bring-your-own-license",
            )
        ],
        [
            _reservation(
                "ri-ora",
                "db.r6i.large",
                engine="oracle-ee",
                product_description="oracle-ee (bring-your-own-license)",
            )
        ],
        at=NOW,
    )
    assert byol.instances[0].coverage_status == COVERAGE_PARTIAL

    license_included = RdsReservationCoverageEngine().analyze(
        [
            _instance(
                "ora-b",
                "db.r6i.xlarge",
                engine="oracle-ee",
                license_model="license-included",
            )
        ],
        [
            _reservation(
                "ri-ora-li",
                "db.r6i.large",
                engine="oracle-ee",
                product_description="oracle-ee (license-included)",
            )
        ],
        at=NOW,
    )
    assert license_included.instances[0].coverage_status == COVERAGE_UNCOVERED


def test_oracle_li_shorthand_is_not_treated_as_byol() -> None:
    decision = RdsReservationMatcher().match(
        _reservation(
            "ri-oracle-li",
            "db.r6i.large",
            engine="oracle-ee",
            product_description="oracle-ee(li)",
        ),
        _instance(
            "db-oracle-byol",
            "db.r6i.large",
            engine="oracle-ee",
            license_model="bring-your-own-license",
        ),
        at=NOW,
    )
    assert not decision.compatible
    assert decision.reason == "LICENSE_MISMATCH"


def test_license_mismatch_does_not_cover_oracle() -> None:
    matcher = RdsReservationMatcher()
    decision = matcher.match(
        _reservation(
            "ri-ora",
            "db.r6i.large",
            engine="oracle-ee",
            product_description="oracle-ee (bring-your-own-license)",
        ),
        _instance(
            "ora-a",
            "db.r6i.large",
            engine="oracle-ee",
            license_model="license-included",
        ),
        at=NOW,
    )
    assert not decision.compatible
    assert decision.reason == "LICENSE_MISMATCH"


def test_single_multi_az_and_logical_cluster_units() -> None:
    single = _instance("single", "db.r6g.large")
    multi = _instance("multi", "db.r6g.large", multi_az=True)
    cluster = _instance("cluster", "db.m6gd.large", topology="multi_az_cluster")
    member = _instance("member", "db.m6gd.large", topology="multi_az_cluster_member")
    assert instance_required_units(single)[0] == Decimal("4")
    assert instance_required_units(multi)[0] == Decimal("8")
    assert instance_required_units(cluster)[0] == Decimal("12")
    assert instance_required_units(member)[0] == Decimal("4")


def test_multi_az_reservation_capacity_is_two_times_base_units() -> None:
    reservation = _reservation("ri-multi", "db.r6g.large", multi_az=True, count=2)
    assert reservation_total_units(reservation)[0] == Decimal("16")


def test_aurora_standard_and_io_optimized() -> None:
    standard = _instance(
        "aurora-a",
        "db.r6g.large",
        engine="aurora-mysql",
        license_model="general-public-license",
        topology="aurora_cluster",
        storage="aurora",
    )
    optimized = _instance(
        "aurora-b",
        "db.r6g.large",
        engine="aurora-mysql",
        license_model="general-public-license",
        topology="aurora_cluster",
        storage="aurora-iopt1",
    )
    assert instance_required_units(standard)[0] == Decimal("4")
    assert instance_required_units(optimized)[0] == Decimal("5.2")


def test_aurora_unknown_storage_is_unknown_not_assumed_standard() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [
            _instance(
                "aurora-a",
                "db.r6g.large",
                engine="aurora-mysql",
                license_model="general-public-license",
                topology="aurora_cluster",
                storage=None,
            )
        ],
        [_reservation("ri-a", "db.r6g.large", engine="aurora-mysql")],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_UNKNOWN


def test_partial_coverage_and_no_double_counting() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [
            _instance("db-a", "db.r6g.large", row_id=1),
            _instance("db-b", "db.r6g.xlarge", row_id=2),
        ],
        [_reservation("ri-1", "db.r6g.large", count=2)],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_FULL
    assert result.instances[0].covered_units == Decimal("4")
    assert result.instances[1].coverage_status == COVERAGE_PARTIAL
    assert result.instances[1].covered_units == Decimal("4")
    assert sum((a.units for a in result.allocations), Decimal("0")) == Decimal("8")


def test_unused_reservation_capacity() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [_instance("db-a", "db.r6g.xlarge")],
        [_reservation("ri-1", "db.r6g.2xlarge")],
        at=NOW,
    )
    utilization = result.reservations[0]
    assert utilization.total_units == Decimal("16")
    assert utilization.allocated_units == Decimal("8")
    assert utilization.unused_units == Decimal("8")
    assert utilization.utilization_percentage == Decimal("50")


def test_transient_state_remains_eligible_but_stopped_does_not() -> None:
    result = RdsReservationCoverageEngine().analyze(
        [
            _instance("db-mod", "db.r6g.large", row_id=1, status="modifying"),
            _instance("db-stop", "db.r6g.large", row_id=2, status="stopped"),
        ],
        [_reservation("ri-1", "db.r6g.large")],
        at=NOW,
    )
    assert len(result.instances) == 1
    assert result.instances[0].instance.db_instance_identifier == "db-mod"


def test_expired_reservation_is_not_available() -> None:
    reservation = _reservation("ri-old", "db.r6g.large")
    reservation.expiration_at = NOW - timedelta(seconds=1)
    result = RdsReservationCoverageEngine().analyze(
        [_instance("db-a", "db.r6g.large")], [reservation], at=NOW
    )
    assert result.instances[0].coverage_status == COVERAGE_UNCOVERED
    assert not result.reservations


def test_verified_cross_account_allocation_is_supported() -> None:
    context = BillingScopeContext(
        scope_by_account={"111111111111": "o-example", "222222222222": "o-example"},
        sharing_enabled_by_account={"111111111111": True, "222222222222": True},
    )
    result = RdsReservationCoverageEngine(context).analyze(
        [_instance("db-a", "db.r6g.large", account="222222222222")],
        [_reservation("ri-1", "db.r6g.large", account="111111111111")],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_FULL
    assert result.allocations[0].allocation_scope == CROSS_ACCOUNT_VERIFIED


def test_unknown_cross_account_sharing_does_not_create_false_positive() -> None:
    context = BillingScopeContext(
        scope_by_account={"111111111111": "o-example", "222222222222": "o-example"}
    )
    result = RdsReservationCoverageEngine(context).analyze(
        [_instance("db-a", "db.r6g.large", account="222222222222")],
        [_reservation("ri-1", "db.r6g.large", account="111111111111")],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_UNCOVERED


def test_different_billing_scopes_do_not_share() -> None:
    context = BillingScopeContext(
        scope_by_account={"111111111111": "o-one", "222222222222": "o-two"},
        sharing_enabled_by_account={"111111111111": True, "222222222222": True},
    )
    result = RdsReservationCoverageEngine(context).analyze(
        [_instance("db-a", "db.r6g.large", account="222222222222")],
        [_reservation("ri-1", "db.r6g.large", account="111111111111")],
        at=NOW,
    )
    assert result.instances[0].coverage_status == COVERAGE_UNCOVERED


def test_engine_is_deterministic_and_idempotent() -> None:
    instances = [
        _instance("db-b", "db.r6g.xlarge", row_id=2),
        _instance("db-a", "db.r6g.large", row_id=1),
    ]
    reservations = [
        _reservation("ri-b", "db.r6g.large", row_id=2),
        _reservation("ri-a", "db.r6g.xlarge", row_id=1),
    ]
    engine = RdsReservationCoverageEngine()
    first = engine.analyze(instances, reservations, at=NOW)
    second = engine.analyze(reversed(instances), reversed(reservations), at=NOW)

    first_semantic = [
        (
            item.instance.db_instance_identifier,
            item.required_units,
            item.covered_units,
            item.coverage_status,
        )
        for item in first.instances
    ]
    second_semantic = [
        (
            item.instance.db_instance_identifier,
            item.required_units,
            item.covered_units,
            item.coverage_status,
        )
        for item in second.instances
    ]
    assert first_semantic == second_semantic
    assert all(item.coverage_percentage <= Decimal("100") for item in first.instances)
    assert all(item.unused_units >= 0 for item in first.reservations)
