from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.rds_coverage import (
    RdsInstanceReservationCoverage,
    RdsReservationAllocation,
    RdsReservationCoverageRun,
    RdsReservationUtilization,
)
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.opportunity_fingerprint import build_opportunity_fingerprint
from app.services.rds_inventory import normalize_rds_engine
from app.services.rds_reservation_rules import (
    COVERAGE_FULL,
    COVERAGE_PARTIAL,
    COVERAGE_UNCOVERED,
    COVERAGE_UNKNOWN,
    is_active_reservation,
    is_reservation_coverage_eligible_instance,
)

logger = logging.getLogger(__name__)

RDS_RESERVATION_UNCOVERED = "RDS_RESERVATION_UNCOVERED"
RDS_RESERVATION_PARTIAL_COVERAGE = "RDS_RESERVATION_PARTIAL_COVERAGE"
RDS_RESERVATION_UNUSED_CAPACITY = "RDS_RESERVATION_UNUSED_CAPACITY"
RDS_RESERVATION_EXPIRING = "RDS_RESERVATION_EXPIRING"

RDS_RESERVATION_RULES = frozenset(
    {
        RDS_RESERVATION_UNCOVERED,
        RDS_RESERVATION_PARTIAL_COVERAGE,
        RDS_RESERVATION_UNUSED_CAPACITY,
        RDS_RESERVATION_EXPIRING,
    }
)
COVERAGE_RULES = frozenset(
    {RDS_RESERVATION_UNCOVERED, RDS_RESERVATION_PARTIAL_COVERAGE}
)
RESERVATION_RULES = frozenset(
    {RDS_RESERVATION_UNUSED_CAPACITY, RDS_RESERVATION_EXPIRING}
)
ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
FINGERPRINT_SCOPE = "rds-reservation"


@dataclass
class RdsReservationOpportunityResult:
    coverage_run_id: int
    created: int = 0
    updated: int = 0
    resolved: int = 0
    unchanged: int = 0
    uncovered_found: int = 0
    partial_found: int = 0
    unused_capacity_found: int = 0
    expiring_found: int = 0
    unknown_skipped: int = 0
    stale_skipped: int = 0
    uncertain: int = 0
    errors: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now(value: datetime | None = None) -> datetime:
    return _utc(value or utcnow())


def _fresh(collected_at: datetime | None, *, now: datetime) -> bool:
    if collected_at is None:
        return False
    threshold = timedelta(hours=settings.rds_reservation_inventory_freshness_hours)
    return _utc(collected_at) >= now - threshold


def _decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _number(value: Decimal | int | float | str | None) -> float:
    return float(_decimal(value))


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= ZERO:
        return ZERO
    return max(ZERO, min(ONE_HUNDRED, numerator / denominator * ONE_HUNDRED))


def _fingerprint(
    *,
    account_id: str,
    region: str,
    resource_id: str,
    rule_key: str,
) -> str:
    return build_opportunity_fingerprint(
        provider="aws",
        account_id=account_id,
        region=region,
        resource_id=resource_id,
        rule_id=rule_key,
        scope=FINGERPRINT_SCOPE,
    )


def _run_marker(run_id: int) -> str:
    return f"rds-coverage:{run_id}"


def _expiration_delta(reservation: AwsRdsReservedInstance, *, now: datetime) -> timedelta:
    return _utc(reservation.expiration_at) - now


def _days_until_expiration(
    reservation: AwsRdsReservedInstance, *, now: datetime
) -> int:
    seconds = _expiration_delta(reservation, now=now).total_seconds()
    if seconds <= 0:
        return 0 if seconds == 0 else -math.ceil(abs(seconds) / 86400)
    return math.ceil(seconds / 86400)


def _active_for_expiration(
    reservation: AwsRdsReservedInstance, *, now: datetime
) -> bool:
    start = _utc(reservation.start_time)
    expiration = _utc(reservation.expiration_at)
    return (
        bool(reservation.is_active)
        and (reservation.state or "").strip().lower() == "active"
        and start <= now <= expiration
    )


def _expiration_band(days: int) -> str:
    if days <= settings.rds_reservation_expiration_critical_days:
        return "critical"
    if days <= settings.rds_reservation_expiration_high_days:
        return "high"
    if days <= settings.rds_reservation_expiration_warning_days:
        return "medium"
    return "healthy"


def _coverage_severity(uncovered_units: Decimal, percentage: Decimal) -> str:
    if percentage >= Decimal("75") or uncovered_units >= Decimal("16"):
        return "high"
    if percentage >= Decimal("25") or uncovered_units >= Decimal("4"):
        return "medium"
    return "low"


def _unused_severity(
    unused_units: Decimal, utilization_percentage: Decimal
) -> str:
    if utilization_percentage <= Decimal("25") or unused_units >= Decimal("16"):
        return "high"
    if utilization_percentage <= Decimal("60") or unused_units >= Decimal("4"):
        return "medium"
    return "low"


def _expiration_severity(days: int) -> str:
    # DeepOps' global severity taxonomy is high / medium / low.
    return (
        "high"
        if days <= settings.rds_reservation_expiration_high_days
        else "medium"
    )


def _mark_active(finding: Finding, *, run_id: int, now: datetime) -> None:
    finding.presence_status = OpportunityPresenceStatus.ACTIVE.value
    finding.missing_count = 0
    finding.missing_since_at = None
    finding.resolved_externally_at = None
    finding.presence_reconciled_run_id = _run_marker(run_id)
    finding.presence_reconciled_at = now


def _resolve(finding: Finding, *, run_id: int, now: datetime, reason: str) -> bool:
    already = (
        finding.presence_status == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
        and finding.presence_reconciled_run_id == _run_marker(run_id)
    )
    if already:
        return False
    metadata = dict(finding.provider_metadata or {})
    metadata["resolution_reason"] = reason
    metadata["resolved_by_coverage_run_id"] = run_id
    finding.provider_metadata = metadata
    finding.presence_status = OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
    finding.missing_count = 0
    finding.missing_since_at = None
    finding.resolved_externally_at = now
    finding.presence_reconciled_run_id = _run_marker(run_id)
    finding.presence_reconciled_at = now
    return True


def _mark_uncertain(
    finding: Finding, *, run_id: int, now: datetime, reason: str
) -> bool:
    marker = _run_marker(run_id)
    if (
        finding.presence_status == OpportunityPresenceStatus.MISSING.value
        and finding.presence_reconciled_run_id == marker
    ):
        return False
    metadata = dict(finding.provider_metadata or {})
    metadata["presence_uncertain_reason"] = reason
    metadata["presence_uncertain_coverage_run_id"] = run_id
    finding.provider_metadata = metadata
    if finding.presence_status != OpportunityPresenceStatus.MISSING.value:
        finding.missing_since_at = now
    finding.presence_status = OpportunityPresenceStatus.MISSING.value
    finding.missing_count = int(finding.missing_count or 0) + 1
    finding.resolved_externally_at = None
    finding.presence_reconciled_run_id = marker
    finding.presence_reconciled_at = now
    return True


def _upsert(
    db: Session,
    *,
    run_id: int,
    now: datetime,
    account_id: str,
    region: str,
    resource_id: str,
    resource_name: str | None,
    resource_type: str,
    rule_key: str,
    title: str,
    description: str,
    severity: str,
    provider_metadata: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[Finding, str]:
    fingerprint = _fingerprint(
        account_id=account_id,
        region=region,
        resource_id=resource_id,
        rule_key=rule_key,
    )
    finding = (
        db.query(Finding)
        .filter(Finding.fingerprint == fingerprint)
        .with_for_update()
        .one_or_none()
    )
    created = False
    if finding is None:
        candidate = Finding(
            fingerprint=fingerprint,
            provider="aws",
            account_id=account_id,
            rule_key=rule_key,
            service="rds",
            region=region,
            resource_id=resource_id,
            resource_name=resource_name,
            resource_type=resource_type,
            provider_metadata=provider_metadata,
            title=title,
            description=description,
            evidence=evidence,
            current_monthly_cost=ZERO,
            estimated_monthly_savings=ZERO,
            currency="USD",
            confidence="high",
            severity=severity,
            status="open",
            first_seen_at=now,
            last_seen_at=now,
            total_occurrence_count=1,
        )
        _mark_active(candidate, run_id=run_id, now=now)
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            finding = candidate
            created = True
        except IntegrityError:
            finding = (
                db.query(Finding)
                .filter(Finding.fingerprint == fingerprint)
                .with_for_update()
                .one()
            )

    if created:
        return finding, "created"

    previous_run = (finding.provider_metadata or {}).get("coverage_run_id")
    was_same = (
        previous_run == run_id
        and finding.provider_metadata == provider_metadata
        and finding.evidence == evidence
        and finding.title == title
        and finding.description == description
        and finding.severity == severity
        and finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
    )
    finding.resource_name = resource_name
    finding.resource_type = resource_type
    finding.provider_metadata = provider_metadata
    finding.title = title
    finding.description = description
    finding.evidence = evidence
    finding.severity = severity
    finding.confidence = "high"
    finding.current_monthly_cost = ZERO
    finding.estimated_monthly_savings = ZERO
    finding.last_seen_at = now
    if previous_run != run_id:
        finding.total_occurrence_count = int(finding.total_occurrence_count or 0) + 1
    _mark_active(finding, run_id=run_id, now=now)
    return finding, "unchanged" if was_same else "updated"


def _record_action(result: RdsReservationOpportunityResult, action: str) -> None:
    if action == "created":
        result.created += 1
    elif action == "updated":
        result.updated += 1
    else:
        result.unchanged += 1


def _account_names(db: Session) -> dict[int, str]:
    return {row.id: row.name for row in db.query(CloudAccount).all()}


def _coverage_metadata(
    coverage: RdsInstanceReservationCoverage,
    instance: AwsRdsInstance,
    *,
    account_name: str | None,
    allocations: list[dict[str, Any]],
    run: RdsReservationCoverageRun,
    generated_at: datetime,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "category": "reservation",
        "finding_family": "rds_reservation",
        "coverage_run_id": run.id,
        "inventory_timestamp": _utc(instance.collected_at).isoformat(),
        "coverage_calculated_at": _utc(run.completed_at or run.started_at).isoformat(),
        "opportunity_generated_at": generated_at.isoformat(),
        "account_name": account_name,
        "coverage_status": coverage.coverage_status,
        "coverage_scope": coverage.coverage_scope,
        "calculation_method": coverage.calculation_method,
        "required_units": _number(coverage.required_units),
        "covered_units": _number(coverage.covered_units),
        "uncovered_units": _number(coverage.uncovered_units),
        "coverage_percentage": _number(coverage.coverage_percentage),
        "engine": instance.engine_normalized,
        "engine_version": instance.engine_version,
        "instance_class": instance.db_instance_class,
        "instance_family": instance.instance_family,
        "instance_size": instance.instance_size,
        "multi_az": bool(instance.multi_az),
        "deployment_topology": instance.deployment_topology,
        "license_model": instance.license_model,
        "db_instance_identifier": instance.db_instance_identifier,
        "db_instance_arn": instance.db_instance_arn,
        "allocation_ids": [item["allocation_id"] for item in allocations],
        "reservation_ids": [item["reservation_id"] for item in allocations],
        "allocations": allocations,
        "technical_explanation": coverage.explanation or {},
        "recommended_action": recommendation,
        "savings_status": "not_calculated",
        "recommendation_scope": "analysis_only",
    }


def _reservation_metadata(
    utilization: RdsReservationUtilization,
    reservation: AwsRdsReservedInstance,
    *,
    account_name: str | None,
    workloads: list[dict[str, Any]],
    run: RdsReservationCoverageRun,
    generated_at: datetime,
    days: int,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "category": "reservation",
        "finding_family": "rds_reservation",
        "coverage_run_id": run.id,
        "inventory_timestamp": _utc(reservation.collected_at).isoformat(),
        "coverage_calculated_at": _utc(run.completed_at or run.started_at).isoformat(),
        "opportunity_generated_at": generated_at.isoformat(),
        "account_name": account_name,
        "reservation_id": reservation.reserved_db_instance_id,
        "reservation_db_id": reservation.id,
        "engine": reservation.engine_normalized,
        "instance_class": reservation.db_instance_class,
        "instance_family": reservation.instance_family,
        "instance_size": reservation.instance_size,
        "multi_az": bool(reservation.multi_az),
        "db_instance_count": reservation.instance_count,
        "offering_type": reservation.offering_type,
        "offering_class": reservation.offering_class,
        "state": reservation.state,
        "start_time": _utc(reservation.start_time).isoformat(),
        "expiration_at": _utc(reservation.expiration_at).isoformat(),
        "days_until_expiration": days,
        "reserved_units": _number(utilization.total_units),
        "allocated_units": _number(utilization.allocated_units),
        "unused_units": _number(utilization.unused_units),
        "utilization_percentage": _number(utilization.utilization_percentage),
        "associated_workloads": workloads,
        "recommended_action": recommendation,
        "savings_status": "not_calculated",
        "recommendation_scope": "analysis_only",
    }


def _existing_by_fingerprint(db: Session) -> dict[str, Finding]:
    rows = (
        db.query(Finding)
        .filter(
            Finding.provider == "aws",
            Finding.service == "rds",
            Finding.rule_key.in_(RDS_RESERVATION_RULES),
            Finding.archived_at.is_(None),
        )
        .all()
    )
    return {row.fingerprint: row for row in rows}


def generate_rds_reservation_opportunities(
    db: Session,
    *,
    coverage_run_id: int | None = None,
    now: datetime | None = None,
) -> RdsReservationOpportunityResult:
    generated_at = _now(now)
    started_clock = time.monotonic()
    run = (
        db.get(RdsReservationCoverageRun, coverage_run_id)
        if coverage_run_id is not None
        else (
            db.query(RdsReservationCoverageRun)
            .filter(RdsReservationCoverageRun.status == "COMPLETED")
            .order_by(RdsReservationCoverageRun.id.desc())
            .first()
        )
    )
    if run is None or run.status != "COMPLETED":
        raise ValueError("A completed RDS reservation coverage run is required")

    result = RdsReservationOpportunityResult(coverage_run_id=run.id)
    tolerance = settings.rds_reservation_unused_units_tolerance
    account_names = _account_names(db)

    coverage_rows = (
        db.query(RdsInstanceReservationCoverage, AwsRdsInstance)
        .join(AwsRdsInstance, AwsRdsInstance.id == RdsInstanceReservationCoverage.rds_instance_id)
        .filter(RdsInstanceReservationCoverage.coverage_run_id == run.id)
        .order_by(
            RdsInstanceReservationCoverage.account_id,
            RdsInstanceReservationCoverage.region,
            AwsRdsInstance.db_instance_identifier,
        )
        .all()
    )
    utilization_rows = (
        db.query(RdsReservationUtilization, AwsRdsReservedInstance)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationUtilization.reservation_id,
        )
        .filter(RdsReservationUtilization.coverage_run_id == run.id)
        .order_by(
            AwsRdsReservedInstance.account_id,
            AwsRdsReservedInstance.region,
            AwsRdsReservedInstance.reserved_db_instance_id,
        )
        .all()
    )
    allocation_rows = (
        db.query(
            RdsReservationAllocation,
            AwsRdsReservedInstance,
            AwsRdsInstance,
        )
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationAllocation.reservation_id,
        )
        .join(
            AwsRdsInstance,
            AwsRdsInstance.id == RdsReservationAllocation.rds_instance_id,
        )
        .filter(RdsReservationAllocation.coverage_run_id == run.id)
        .order_by(RdsReservationAllocation.id)
        .all()
    )

    allocations_by_instance: dict[int, list[dict[str, Any]]] = defaultdict(list)
    workloads_by_reservation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for allocation, reservation, instance in allocation_rows:
        item = {
            "allocation_id": allocation.id,
            "reservation_id": reservation.reserved_db_instance_id,
            "reservation_db_id": reservation.id,
            "allocated_units": _number(allocation.allocated_units),
            "match_type": allocation.match_type,
            "allocation_scope": allocation.allocation_scope,
            "reason": allocation.reason or {},
        }
        allocations_by_instance[instance.id].append(item)
        workloads_by_reservation[reservation.id].append(
            {
                "allocation_id": allocation.id,
                "db_instance_identifier": instance.db_instance_identifier,
                "db_instance_arn": instance.db_instance_arn,
                "allocated_units": _number(allocation.allocated_units),
                "match_type": allocation.match_type,
                "allocation_scope": allocation.allocation_scope,
            }
        )

    existing = _existing_by_fingerprint(db)
    observed: set[str] = set()
    uncertain: set[str] = set()
    current_instance_keys: set[tuple[str, str, str]] = set()
    current_reservation_keys: set[tuple[str, str, str]] = set()

    for coverage, instance in coverage_rows:
        key = (instance.account_id, instance.region, instance.db_instance_identifier)
        current_instance_keys.add(key)
        fingerprints = {
            rule: _fingerprint(
                account_id=instance.account_id,
                region=instance.region,
                resource_id=instance.db_instance_identifier,
                rule_key=rule,
            )
            for rule in COVERAGE_RULES
        }
        if not _fresh(instance.collected_at, now=generated_at):
            result.stale_skipped += 1
            uncertain.update(fingerprints.values())
            continue
        if coverage.coverage_status == COVERAGE_UNKNOWN:
            result.unknown_skipped += 1
            uncertain.update(fingerprints.values())
            continue
        if not is_reservation_coverage_eligible_instance(instance):
            continue

        required = _decimal(coverage.required_units)
        covered = _decimal(coverage.covered_units)
        uncovered = _decimal(coverage.uncovered_units)
        allocations = allocations_by_instance.get(instance.id, [])
        rule_key: str | None = None
        if coverage.coverage_status == COVERAGE_UNCOVERED and required > ZERO and covered <= ZERO:
            rule_key = RDS_RESERVATION_UNCOVERED
            title = "RDS sem cobertura de Reserved Instance"
            description = (
                f"O RDS {instance.db_instance_identifier} não possui capacidade compatível "
                "de Reserved DB Instance atualmente alocada."
            )
            recommendation = (
                "Avaliar contratação de Reserved DB Instance compatível caso o workload "
                "possua utilização estável."
            )
            result.uncovered_found += 1
        elif coverage.coverage_status == COVERAGE_PARTIAL and ZERO < covered < required:
            rule_key = RDS_RESERVATION_PARTIAL_COVERAGE
            title = "RDS com cobertura parcial de Reserved Instance"
            description = (
                f"O RDS {instance.db_instance_identifier} possui "
                f"{_number(coverage.coverage_percentage):g}% de cobertura. "
                f"{_number(uncovered):g} de {_number(required):g} normalized units "
                "permanecem descobertas."
            )
            recommendation = (
                "Avaliar cobertura adicional para a capacidade atualmente descoberta."
            )
            result.partial_found += 1
        elif coverage.coverage_status == COVERAGE_FULL:
            continue
        else:
            continue

        metadata = _coverage_metadata(
            coverage,
            instance,
            account_name=account_names.get(instance.cloud_account_id),
            allocations=allocations,
            run=run,
            generated_at=generated_at,
            recommendation=recommendation,
        )
        metadata["opportunity_type"] = rule_key
        evidence = {
            "coverage_run_id": run.id,
            "rds_instance_id": instance.id,
            "db_instance_identifier": instance.db_instance_identifier,
            "required_units": _number(required),
            "covered_units": _number(covered),
            "uncovered_units": _number(uncovered),
            "coverage_percentage": _number(coverage.coverage_percentage),
            "coverage_scope": coverage.coverage_scope,
            "allocation_ids": [item["allocation_id"] for item in allocations],
            "reservation_ids": [item["reservation_id"] for item in allocations],
            "calculated_at": _utc(run.completed_at or run.started_at).isoformat(),
        }
        _, action = _upsert(
            db,
            run_id=run.id,
            now=generated_at,
            account_id=instance.account_id,
            region=instance.region,
            resource_id=instance.db_instance_identifier,
            resource_name=instance.db_instance_identifier,
            resource_type="aws_rds_db_instance",
            rule_key=rule_key,
            title=title,
            description=description,
            severity=_coverage_severity(
                uncovered,
                ONE_HUNDRED - _decimal(coverage.coverage_percentage),
            ),
            provider_metadata=metadata,
            evidence=evidence,
        )
        observed.add(fingerprints[rule_key])
        _record_action(result, action)

    for utilization, reservation in utilization_rows:
        key = (
            reservation.account_id,
            reservation.region,
            reservation.reserved_db_instance_id,
        )
        current_reservation_keys.add(key)
        fingerprints = {
            rule: _fingerprint(
                account_id=reservation.account_id,
                region=reservation.region,
                resource_id=reservation.reserved_db_instance_id,
                rule_key=rule,
            )
            for rule in RESERVATION_RULES
        }
        if not _fresh(reservation.collected_at, now=generated_at):
            result.stale_skipped += 1
            uncertain.update(fingerprints.values())
            continue

        total_units = _decimal(utilization.total_units)
        allocated_units = _decimal(utilization.allocated_units)
        unused_units = _decimal(utilization.unused_units)
        utilization_pct = _decimal(utilization.utilization_percentage)
        days = _days_until_expiration(reservation, now=generated_at)
        workloads = workloads_by_reservation.get(reservation.id, [])

        if unused_units > tolerance:
            recommendation = (
                "Revisar a capacidade reservada em relação ao inventário atual antes "
                "de novas aquisições ou renovações."
            )
            metadata = _reservation_metadata(
                utilization,
                reservation,
                account_name=account_names.get(reservation.cloud_account_id),
                workloads=workloads,
                run=run,
                generated_at=generated_at,
                days=days,
                recommendation=recommendation,
            )
            metadata["opportunity_type"] = RDS_RESERVATION_UNUSED_CAPACITY
            description = (
                f"A reserva {reservation.reserved_db_instance_id} possui "
                f"{_number(total_units):g} normalized units, "
                f"{_number(allocated_units):g} utilizadas e "
                f"{_number(unused_units):g} disponíveis."
            )
            _, action = _upsert(
                db,
                run_id=run.id,
                now=generated_at,
                account_id=reservation.account_id,
                region=reservation.region,
                resource_id=reservation.reserved_db_instance_id,
                resource_name=reservation.reserved_db_instance_id,
                resource_type="aws_rds_reserved_db_instance",
                rule_key=RDS_RESERVATION_UNUSED_CAPACITY,
                title="Capacidade de RDS Reserved Instance não utilizada",
                description=description,
                severity=_unused_severity(unused_units, utilization_pct),
                provider_metadata=metadata,
                evidence={
                    "coverage_run_id": run.id,
                    "reservation_db_id": reservation.id,
                    "reservation_id": reservation.reserved_db_instance_id,
                    "reserved_units": _number(total_units),
                    "allocated_units": _number(allocated_units),
                    "unused_units": _number(unused_units),
                    "utilization_percentage": _number(utilization_pct),
                    "allocation_ids": [item["allocation_id"] for item in workloads],
                    "calculated_at": _utc(run.completed_at or run.started_at).isoformat(),
                },
            )
            observed.add(fingerprints[RDS_RESERVATION_UNUSED_CAPACITY])
            _record_action(result, action)
            result.unused_capacity_found += 1

        delta = _expiration_delta(reservation, now=generated_at)
        if (
            _active_for_expiration(reservation, now=generated_at)
            and timedelta(0) <= delta
            <= timedelta(days=settings.rds_reservation_expiration_warning_days)
        ):
            days = _days_until_expiration(reservation, now=generated_at)
            used = allocated_units > settings.rds_reservation_unused_units_tolerance
            recommendation = (
                "Avaliar renovação ou substituição da reserva antes do vencimento."
                if used
                else "Revisar a necessidade da reserva antes de renovar."
            )
            metadata = _reservation_metadata(
                utilization,
                reservation,
                account_name=account_names.get(reservation.cloud_account_id),
                workloads=workloads,
                run=run,
                generated_at=generated_at,
                days=days,
                recommendation=recommendation,
            )
            metadata.update(
                {
                    "opportunity_type": RDS_RESERVATION_EXPIRING,
                    "expiration_band": _expiration_band(days),
                }
            )
            description = (
                f"A reserva {reservation.reserved_db_instance_id} expira em {days} "
                f"{'dia' if days == 1 else 'dias'} e atualmente possui "
                f"{_number(utilization_pct):g}% de utilização."
            )
            _, action = _upsert(
                db,
                run_id=run.id,
                now=generated_at,
                account_id=reservation.account_id,
                region=reservation.region,
                resource_id=reservation.reserved_db_instance_id,
                resource_name=reservation.reserved_db_instance_id,
                resource_type="aws_rds_reserved_db_instance",
                rule_key=RDS_RESERVATION_EXPIRING,
                title="RDS Reserved Instance próxima do vencimento",
                description=description,
                severity=_expiration_severity(days),
                provider_metadata=metadata,
                evidence={
                    "coverage_run_id": run.id,
                    "reservation_db_id": reservation.id,
                    "reservation_id": reservation.reserved_db_instance_id,
                    "expiration_at": _utc(reservation.expiration_at).isoformat(),
                    "days_until_expiration": days,
                    "reserved_units": _number(total_units),
                    "allocated_units": _number(allocated_units),
                    "unused_units": _number(unused_units),
                    "utilization_percentage": _number(utilization_pct),
                    "allocation_ids": [item["allocation_id"] for item in workloads],
                    "calculated_at": _utc(run.completed_at or run.started_at).isoformat(),
                },
            )
            observed.add(fingerprints[RDS_RESERVATION_EXPIRING])
            _record_action(result, action)
            result.expiring_found += 1

    # Stale/UNKNOWN data is deliberately non-authoritative. Existing findings become
    # "missing" instead of being falsely resolved or kept as a strong active conclusion.
    for fingerprint in uncertain:
        finding = existing.get(fingerprint)
        if (
            finding is not None
            and fingerprint not in observed
            and _mark_uncertain(
                finding,
                run_id=run.id,
                now=generated_at,
                reason="STALE_OR_UNKNOWN_RDS_RESERVATION_DATA",
            )
        ):
            result.uncertain += 1

    instances_by_key = {
        (row.account_id, row.region, row.db_instance_identifier): row
        for row in db.query(AwsRdsInstance).all()
    }
    reservations_by_key = {
        (row.account_id, row.region, row.reserved_db_instance_id): row
        for row in db.query(AwsRdsReservedInstance).all()
    }

    for fingerprint, finding in existing.items():
        if fingerprint in observed or fingerprint in uncertain:
            continue
        key = (finding.account_id, finding.region or "", finding.resource_id)
        if finding.rule_key in COVERAGE_RULES:
            if key in current_instance_keys:
                authoritative = True
                reason = "COVERAGE_STATE_CHANGED"
            else:
                inventory = instances_by_key.get(key)
                authoritative = bool(
                    inventory
                    and _fresh(inventory.collected_at, now=generated_at)
                    and (
                        not inventory.is_active
                        or not is_reservation_coverage_eligible_instance(inventory)
                    )
                )
                reason = "RDS_INACTIVE_OR_NOT_ELIGIBLE"
        else:
            if key in current_reservation_keys:
                authoritative = True
                reason = "RESERVATION_STATE_CHANGED"
            else:
                reservation = reservations_by_key.get(key)
                authoritative = bool(
                    reservation
                    and _fresh(reservation.collected_at, now=generated_at)
                    and (
                        not reservation.is_active
                        or not is_active_reservation(reservation, at=generated_at)
                    )
                )
                reason = "RESERVATION_INACTIVE_OR_EXPIRED"

        if authoritative:
            if _resolve(finding, run_id=run.id, now=generated_at, reason=reason):
                result.resolved += 1
        else:
            if _mark_uncertain(
                finding,
                run_id=run.id,
                now=generated_at,
                reason="RESOURCE_NOT_AUTHORITATIVELY_PRESENT_IN_COVERAGE_RUN",
            ):
                result.uncertain += 1

    result.duration_ms = int((time.monotonic() - started_clock) * 1000)
    logger.info(
        "RDS reservation opportunities run=%s created=%s updated=%s resolved=%s "
        "uncovered=%s partial=%s unused=%s expiring=%s unknown_skipped=%s "
        "stale_skipped=%s uncertain=%s duration_ms=%s",
        run.id,
        result.created,
        result.updated,
        result.resolved,
        result.uncovered_found,
        result.partial_found,
        result.unused_capacity_found,
        result.expiring_found,
        result.unknown_skipped,
        result.stale_skipped,
        result.uncertain,
        result.duration_ms,
    )
    return result


def rds_reservation_opportunity_summary(
    db: Session,
    *,
    coverage_run_id: int | None = None,
    account: str | None = None,
    region: str | None = None,
    engine: str | None = None,
    family: str | None = None,
    instance_class: str | None = None,
    opportunity_status: str | None = None,
    severity: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = _now(now)
    run = (
        db.get(RdsReservationCoverageRun, coverage_run_id)
        if coverage_run_id is not None
        else (
            db.query(RdsReservationCoverageRun)
            .filter(RdsReservationCoverageRun.status == "COMPLETED")
            .order_by(RdsReservationCoverageRun.id.desc())
            .first()
        )
    )
    if run is None or run.status != "COMPLETED":
        raise ValueError("A completed RDS reservation coverage run is required")

    coverage_query = (
        db.query(RdsInstanceReservationCoverage, AwsRdsInstance)
        .join(AwsRdsInstance, AwsRdsInstance.id == RdsInstanceReservationCoverage.rds_instance_id)
        .filter(RdsInstanceReservationCoverage.coverage_run_id == run.id)
    )
    utilization_query = (
        db.query(RdsReservationUtilization, AwsRdsReservedInstance)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationUtilization.reservation_id,
        )
        .filter(RdsReservationUtilization.coverage_run_id == run.id)
    )
    if account:
        coverage_query = coverage_query.filter(RdsInstanceReservationCoverage.account_id == account)
        utilization_query = utilization_query.filter(AwsRdsReservedInstance.account_id == account)
    if region:
        coverage_query = coverage_query.filter(RdsInstanceReservationCoverage.region == region)
        utilization_query = utilization_query.filter(AwsRdsReservedInstance.region == region)
    if engine:
        normalized = normalize_rds_engine(engine)
        coverage_query = coverage_query.filter(AwsRdsInstance.engine_normalized == normalized)
        utilization_query = utilization_query.filter(
            AwsRdsReservedInstance.engine_normalized == normalized
        )
    if family:
        coverage_query = coverage_query.filter(AwsRdsInstance.instance_family == family)
        utilization_query = utilization_query.filter(
            AwsRdsReservedInstance.instance_family == family
        )
    if instance_class:
        coverage_query = coverage_query.filter(
            AwsRdsInstance.db_instance_class == instance_class
        )
        utilization_query = utilization_query.filter(
            AwsRdsReservedInstance.db_instance_class == instance_class
        )

    coverage_rows = coverage_query.all()
    utilization_rows = utilization_query.all()

    statuses = defaultdict(int)
    required = ZERO
    covered = ZERO
    uncovered = ZERO
    for coverage, _ in coverage_rows:
        statuses[coverage.coverage_status] += 1
        required += _decimal(coverage.required_units)
        covered += _decimal(coverage.covered_units)
        uncovered += _decimal(coverage.uncovered_units)

    reserved = ZERO
    allocated = ZERO
    unused = ZERO
    next_7 = 0
    next_15 = 0
    next_30 = 0
    active_reservations = 0
    for utilization, reservation in utilization_rows:
        reserved += _decimal(utilization.total_units)
        allocated += _decimal(utilization.allocated_units)
        unused += _decimal(utilization.unused_units)
        if is_active_reservation(reservation, at=current_time):
            active_reservations += 1
            delta = _expiration_delta(reservation, now=current_time)
            if timedelta(0) <= delta <= timedelta(
                days=settings.rds_reservation_expiration_warning_days
            ):
                days = _days_until_expiration(reservation, now=current_time)
                if days <= settings.rds_reservation_expiration_critical_days:
                    next_7 += 1
                if days <= settings.rds_reservation_expiration_high_days:
                    next_15 += 1
                next_30 += 1

    findings_query = db.query(Finding).filter(
        Finding.provider == "aws",
        Finding.service == "rds",
        Finding.rule_key.in_(RDS_RESERVATION_RULES),
        Finding.presence_status == OpportunityPresenceStatus.ACTIVE.value,
        Finding.archived_at.is_(None),
    )
    if account:
        findings_query = findings_query.filter(Finding.account_id == account)
    if region:
        findings_query = findings_query.filter(Finding.region == region)
    if opportunity_status:
        findings_query = findings_query.filter(Finding.status == opportunity_status)
    if severity:
        findings_query = findings_query.filter(Finding.severity == severity)

    opportunity_counts = defaultdict(int)
    for finding in findings_query.all():
        metadata = finding.provider_metadata or {}
        if engine and metadata.get("engine") != normalize_rds_engine(engine):
            continue
        if family and metadata.get("instance_family") != family:
            continue
        if instance_class and metadata.get("instance_class") != instance_class:
            continue
        opportunity_counts[finding.rule_key] += 1

    return {
        "coverage_run_id": run.id,
        "generated_at": current_time,
        "inventory_snapshot_at": run.inventory_snapshot_at,
        "rds": {
            "total": len(coverage_rows),
            "fully_covered": statuses[COVERAGE_FULL],
            "partially_covered": statuses[COVERAGE_PARTIAL],
            "uncovered": statuses[COVERAGE_UNCOVERED],
            "unknown": statuses[COVERAGE_UNKNOWN],
        },
        "coverage": {
            "required_units": _number(required),
            "covered_units": _number(covered),
            "uncovered_units": _number(uncovered),
            "coverage_percentage": _number(_percentage(covered, required)),
        },
        "reservations": {
            "active": active_reservations,
            "reserved_units": _number(reserved),
            "used_units": _number(allocated),
            "unused_units": _number(unused),
        },
        "expirations": {
            "next_7_days": next_7,
            "next_15_days": next_15,
            "next_30_days": next_30,
        },
        "opportunities": {
            "uncovered": opportunity_counts[RDS_RESERVATION_UNCOVERED],
            "partial": opportunity_counts[RDS_RESERVATION_PARTIAL_COVERAGE],
            "unused_capacity": opportunity_counts[RDS_RESERVATION_UNUSED_CAPACITY],
            "expiring": opportunity_counts[RDS_RESERVATION_EXPIRING],
            "active_total": sum(opportunity_counts.values()),
        },
        "filters": {
            "account": account,
            "region": region,
            "engine": normalize_rds_engine(engine) if engine else None,
            "family": family,
            "instance_class": instance_class,
            "opportunity_status": opportunity_status,
            "severity": severity,
        },
    }
