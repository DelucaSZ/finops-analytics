from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_inventory import is_rds_coverage_eligible, normalize_rds_engine

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
AURORA_IO_OPTIMIZED_MULTIPLIER = Decimal("1.3")

NORMALIZED_UNITS: dict[str, Decimal] = {
    "micro": Decimal("0.5"),
    "small": Decimal("1"),
    "medium": Decimal("2"),
    "large": Decimal("4"),
    "xlarge": Decimal("8"),
    "2xlarge": Decimal("16"),
    "4xlarge": Decimal("32"),
    "6xlarge": Decimal("48"),
    "8xlarge": Decimal("64"),
    "10xlarge": Decimal("80"),
    "12xlarge": Decimal("96"),
    "16xlarge": Decimal("128"),
    "24xlarge": Decimal("192"),
    "32xlarge": Decimal("256"),
}

SIZE_FLEXIBLE_ENGINES = frozenset(
    {
        "mysql",
        "mariadb",
        "postgres",
        "db2-ae",
        "db2-se",
        "aurora-mysql",
        "aurora-postgresql",
    }
)
ORACLE_ENGINES = frozenset(
    {"oracle-ee", "oracle-ee-cdb", "oracle-se", "oracle-se1", "oracle-se2", "oracle-se2-cdb"}
)
SQL_SERVER_ENGINES = frozenset({"sqlserver-ee", "sqlserver-se", "sqlserver-web", "sqlserver-ex"})
ACTIVE_RESERVATION_STATES = frozenset({"active"})

COVERAGE_FULL = "FULL"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_UNCOVERED = "UNCOVERED"
COVERAGE_UNKNOWN = "UNKNOWN"

SAME_ACCOUNT = "SAME_ACCOUNT"
CROSS_ACCOUNT_VERIFIED = "CROSS_ACCOUNT_VERIFIED"
CROSS_ACCOUNT_POTENTIAL = "CROSS_ACCOUNT_POTENTIAL"
NOT_SHAREABLE = "NOT_SHAREABLE"
UNKNOWN_SCOPE = "UNKNOWN"


class UnknownRdsConfiguration(ValueError):
    pass


@dataclass(frozen=True)
class MatchDecision:
    compatible: bool
    match_type: str
    reason: str
    allocation_scope: str = SAME_ACCOUNT


@dataclass
class InstanceDemand:
    row: AwsRdsInstance
    required_units: Decimal
    remaining_units: Decimal
    calculation_method: str
    unknown_reason: str | None = None
    allocations: list[Allocation] = field(default_factory=list)


@dataclass
class ReservationCapacity:
    row: AwsRdsReservedInstance
    total_units: Decimal
    remaining_units: Decimal
    calculation_method: str
    unknown_reason: str | None = None


@dataclass(frozen=True)
class Allocation:
    reservation: AwsRdsReservedInstance
    instance: AwsRdsInstance
    units: Decimal
    match_type: str
    allocation_scope: str
    reason: str


@dataclass(frozen=True)
class InstanceCoverageResult:
    instance: AwsRdsInstance
    required_units: Decimal
    covered_units: Decimal
    uncovered_units: Decimal
    coverage_percentage: Decimal
    coverage_status: str
    coverage_scope: str
    calculation_method: str
    allocations: tuple[Allocation, ...]
    explanation: dict[str, Any]


@dataclass(frozen=True)
class ReservationUtilizationResult:
    reservation: AwsRdsReservedInstance
    total_units: Decimal
    allocated_units: Decimal
    unused_units: Decimal
    utilization_percentage: Decimal


@dataclass(frozen=True)
class CoverageAnalysis:
    instances: tuple[InstanceCoverageResult, ...]
    reservations: tuple[ReservationUtilizationResult, ...]
    allocations: tuple[Allocation, ...]


@dataclass(frozen=True)
class BillingScopeContext:
    scope_by_account: dict[str, str] = field(default_factory=dict)
    sharing_enabled_by_account: dict[str, bool | None] = field(default_factory=dict)

    def relationship(self, reservation_account: str, instance_account: str) -> str:
        if reservation_account == instance_account:
            return SAME_ACCOUNT
        reservation_scope = self.scope_by_account.get(reservation_account)
        instance_scope = self.scope_by_account.get(instance_account)
        if not reservation_scope or not instance_scope:
            return UNKNOWN_SCOPE
        if reservation_scope != instance_scope:
            return NOT_SHAREABLE
        reservation_sharing = self.sharing_enabled_by_account.get(reservation_account)
        instance_sharing = self.sharing_enabled_by_account.get(instance_account)
        if reservation_sharing is True and instance_sharing is True:
            return CROSS_ACCOUNT_VERIFIED
        if reservation_sharing is False or instance_sharing is False:
            return NOT_SHAREABLE
        return CROSS_ACCOUNT_POTENTIAL


def _safe_percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= ZERO:
        return ZERO
    value = numerator / denominator * ONE_HUNDRED
    return min(ONE_HUNDRED, max(ZERO, value))


def normalize_license_model(value: str | None, *, engine: str | None = None) -> str:
    raw = " ".join((value or "").strip().lower().replace("_", "-").split())
    aliases = {
        "li": "license-included",
        "license included": "license-included",
        "license-included": "license-included",
        "byol": "bring-your-own-license",
        "bring your own license": "bring-your-own-license",
        "bring-your-own-license": "bring-your-own-license",
        "general public license": "general-public-license",
        "general-public-license": "general-public-license",
        "postgresql license": "postgresql-license",
        "postgresql-license": "postgresql-license",
        "marketplace license": "marketplace-license",
        "marketplace-license": "marketplace-license",
    }
    normalized = aliases.get(raw, raw)
    if normalized:
        return normalized
    product = normalize_rds_engine(engine)
    if product in {"mysql", "mariadb", "aurora-mysql"}:
        return "general-public-license"
    if product in {"postgres", "aurora-postgresql"}:
        return "postgresql-license"
    return ""


def reservation_license_model(reservation: AwsRdsReservedInstance) -> str:
    text = (reservation.product_description or "").strip().lower()
    if "(li)" in text or text.endswith(" li"):
        return "license-included"
    for token in (
        "bring-your-own-license",
        "bring your own license",
        "license-included",
        "license included",
        "general-public-license",
        "postgresql-license",
        "marketplace-license",
        "byol",
    ):
        if token in text:
            return normalize_license_model(token, engine=reservation.engine_normalized)
    return normalize_license_model(None, engine=reservation.engine_normalized)


def supports_size_flexibility(engine: str, license_model: str) -> bool:
    product = normalize_rds_engine(engine)
    if product in SIZE_FLEXIBLE_ENGINES:
        return True
    return product in ORACLE_ENGINES and license_model == "bring-your-own-license"


def normalized_units_for_size(size: str | None) -> Decimal:
    try:
        return NORMALIZED_UNITS[(size or "").strip().lower()]
    except KeyError as exc:
        raise UnknownRdsConfiguration(f"unsupported DB instance size: {size or '<empty>'}") from exc


def _is_aurora(engine: str) -> bool:
    return normalize_rds_engine(engine) in {"aurora-mysql", "aurora-postgresql"}


def _instance_topology(instance: AwsRdsInstance) -> str:
    explicit = getattr(instance, "deployment_topology", None)
    if explicit:
        return str(explicit)
    if _is_aurora(instance.engine_normalized):
        return "aurora_cluster"
    if instance.cluster_identifier:
        return "unknown_cluster"
    return "multi_az_instance" if instance.multi_az else "single_az"


def _instance_storage_configuration(instance: AwsRdsInstance) -> str | None:
    value = getattr(instance, "cluster_storage_type", None)
    if value:
        return str(value).strip().lower()
    return None


def instance_required_units(instance: AwsRdsInstance) -> tuple[Decimal, str]:
    base = normalized_units_for_size(instance.instance_size)
    engine = normalize_rds_engine(instance.engine_normalized)
    topology = _instance_topology(instance)

    if _is_aurora(engine):
        storage = _instance_storage_configuration(instance)
        if storage in {"aurora-iopt1", "io-optimized", "i/o-optimized", "aurora-io-optimized"}:
            return base * AURORA_IO_OPTIMIZED_MULTIPLIER, "NORMALIZED_UNITS_AURORA_IO_OPTIMIZED"
        if storage in {"aurora", "standard", "aurora-standard"}:
            return base, "NORMALIZED_UNITS_AURORA_STANDARD"
        raise UnknownRdsConfiguration("Aurora storage configuration is unknown")

    multiplier = {
        "single_az": Decimal("1"),
        "multi_az_instance": Decimal("2"),
        "multi_az_cluster": Decimal("3"),
        "multi_az_cluster_member": Decimal("1"),
    }.get(topology)
    if multiplier is None:
        raise UnknownRdsConfiguration(f"unsupported deployment topology: {topology}")
    return base * multiplier, "NORMALIZED_UNITS"


def reservation_total_units(reservation: AwsRdsReservedInstance) -> tuple[Decimal, str]:
    if reservation.instance_count <= 0:
        raise UnknownRdsConfiguration("reservation DBInstanceCount is zero")
    base = normalized_units_for_size(reservation.instance_size)
    engine = normalize_rds_engine(reservation.engine_normalized)
    license_model = reservation_license_model(reservation)
    if supports_size_flexibility(engine, license_model):
        deployment_multiplier = Decimal("1")
        if reservation.multi_az and not _is_aurora(engine):
            deployment_multiplier = Decimal("2")
        return (
            base * Decimal(reservation.instance_count) * deployment_multiplier,
            "NORMALIZED_UNITS",
        )
    deployment_multiplier = Decimal("2") if reservation.multi_az else Decimal("1")
    return (
        base * Decimal(reservation.instance_count) * deployment_multiplier,
        "EXACT_MATCH_CAPACITY",
    )


def is_active_reservation(
    reservation: AwsRdsReservedInstance, *, at: datetime | None = None
) -> bool:
    at = at or datetime.now(UTC)
    start = reservation.start_time
    expiration = reservation.expiration_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    return (
        reservation.is_active
        and (reservation.state or "").strip().lower() in ACTIVE_RESERVATION_STATES
        and start <= at < expiration
    )


_NON_BILLABLE_INSTANCE_STATES = frozenset({"stopped", "stopping", "deleting", "failed"})


def is_reservation_coverage_eligible_instance(instance: AwsRdsInstance) -> bool:
    status = (instance.status or "").strip().lower()
    return (
        instance.is_active
        and status not in _NON_BILLABLE_INSTANCE_STATES
        and is_rds_coverage_eligible(status)
    )


class RdsReservationMatcher:
    def __init__(self, billing_scope: BillingScopeContext | None = None) -> None:
        self.billing_scope = billing_scope or BillingScopeContext()

    def match(
        self,
        reservation: AwsRdsReservedInstance,
        instance: AwsRdsInstance,
        *,
        at: datetime | None = None,
        allow_flexible: bool = True,
    ) -> MatchDecision:
        if not is_active_reservation(reservation, at=at):
            return MatchDecision(False, "incompatible", "RESERVATION_INACTIVE")
        if reservation.region != instance.region:
            return MatchDecision(False, "incompatible", "REGION_MISMATCH")

        reservation_engine = normalize_rds_engine(reservation.engine_normalized)
        instance_engine = normalize_rds_engine(instance.engine_normalized)
        if reservation_engine != instance_engine:
            return MatchDecision(False, "incompatible", "ENGINE_MISMATCH")

        scope = self.billing_scope.relationship(reservation.account_id, instance.account_id)
        if scope not in {SAME_ACCOUNT, CROSS_ACCOUNT_VERIFIED}:
            return MatchDecision(False, "incompatible", scope)

        instance_license = normalize_license_model(instance.license_model, engine=instance_engine)
        reservation_license = reservation_license_model(reservation)
        if reservation_license and instance_license and reservation_license != instance_license:
            return MatchDecision(False, "incompatible", "LICENSE_MISMATCH", scope)

        if reservation.instance_family != instance.instance_family:
            return MatchDecision(False, "incompatible", "FAMILY_MISMATCH", scope)
        if not reservation.instance_family or not instance.instance_family:
            return MatchDecision(False, "incompatible", "UNKNOWN_CONFIGURATION", scope)

        flexible = supports_size_flexibility(instance_engine, instance_license)
        if flexible and allow_flexible:
            try:
                normalized_units_for_size(reservation.instance_size)
                normalized_units_for_size(instance.instance_size)
            except UnknownRdsConfiguration:
                return MatchDecision(False, "incompatible", "UNKNOWN_CONFIGURATION", scope)
            if reservation.db_instance_class == instance.db_instance_class:
                topology = _instance_topology(instance)
                expected_multi_az = topology == "multi_az_instance"
                deployment_converted = (
                    not _is_aurora(instance_engine)
                    and topology != "multi_az_cluster_member"
                    and bool(reservation.multi_az) != expected_multi_az
                )
                if not deployment_converted:
                    return MatchDecision(True, "exact", "EXACT_CLASS_MATCH", scope)
                return MatchDecision(True, "size_flexible", "DEPLOYMENT_SIZE_FLEXIBILITY", scope)
            return MatchDecision(True, "size_flexible", "SIZE_FLEXIBILITY", scope)

        if reservation.db_instance_class != instance.db_instance_class:
            return MatchDecision(False, "incompatible", "SIZE_MISMATCH", scope)

        topology = _instance_topology(instance)
        if topology in {"multi_az_cluster", "multi_az_cluster_member"}:
            return MatchDecision(False, "incompatible", "DEPLOYMENT_MISMATCH", scope)
        expected_multi_az = topology == "multi_az_instance"
        if bool(reservation.multi_az) != expected_multi_az:
            return MatchDecision(False, "incompatible", "DEPLOYMENT_MISMATCH", scope)
        return MatchDecision(True, "exact", "EXACT_MATCH", scope)
