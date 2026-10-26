from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_reservation_rules import (
    COVERAGE_FULL,
    COVERAGE_PARTIAL,
    COVERAGE_UNCOVERED,
    COVERAGE_UNKNOWN,
    CROSS_ACCOUNT_VERIFIED,
    ONE_HUNDRED,
    SAME_ACCOUNT,
    UNKNOWN_SCOPE,
    ZERO,
    Allocation,
    BillingScopeContext,
    CoverageAnalysis,
    InstanceCoverageResult,
    InstanceDemand,
    MatchDecision,
    RdsReservationMatcher,
    ReservationCapacity,
    ReservationUtilizationResult,
    UnknownRdsConfiguration,
    _instance_topology,
    _safe_percentage,
    instance_required_units,
    is_active_reservation,
    is_reservation_coverage_eligible_instance,
    normalize_rds_engine,
    reservation_total_units,
)


class RdsReservationCoverageEngine:
    def __init__(self, billing_scope: BillingScopeContext | None = None) -> None:
        self.matcher = RdsReservationMatcher(billing_scope)

    def analyze(
        self,
        instances: Iterable[AwsRdsInstance],
        reservations: Iterable[AwsRdsReservedInstance],
        *,
        at: datetime | None = None,
    ) -> CoverageAnalysis:
        at = at or datetime.now(UTC)
        demands = [
            self._demand(row)
            for row in instances
            if row.is_active and is_reservation_coverage_eligible_instance(row)
        ]
        capacities = [
            self._capacity(row, at=at) for row in reservations if is_active_reservation(row, at=at)
        ]
        demands.sort(key=self._demand_sort_key)
        capacities.sort(key=self._capacity_sort_key)
        capacity_pools: dict[tuple[str, str, str | None], list[ReservationCapacity]] = defaultdict(
            list
        )
        for capacity in capacities:
            capacity_pools[self._pool_key(capacity.row)].append(capacity)

        all_allocations: list[Allocation] = []
        # Phase 1: stable exact-class allocation.
        # This preserves exact matches before flex conversion.
        for demand in demands:
            if demand.unknown_reason or demand.remaining_units <= ZERO:
                continue
            for capacity in capacity_pools.get(self._pool_key(demand.row), []):
                if capacity.unknown_reason or capacity.remaining_units <= ZERO:
                    continue
                if capacity.row.db_instance_class != demand.row.db_instance_class:
                    continue
                decision = self.matcher.match(capacity.row, demand.row, at=at, allow_flexible=False)
                if not decision.compatible:
                    # Flexible products may convert Single/Multi-AZ while keeping the same class.
                    decision = self.matcher.match(
                        capacity.row, demand.row, at=at, allow_flexible=True
                    )
                    if not decision.compatible or decision.match_type != "exact":
                        continue
                all_allocations.append(self._allocate(capacity, demand, decision))
                if demand.remaining_units <= ZERO:
                    break

        # Phase 2: normalized-unit size flexibility. Capacity is never reset or reused.
        for demand in demands:
            if demand.unknown_reason or demand.remaining_units <= ZERO:
                continue
            for capacity in capacity_pools.get(self._pool_key(demand.row), []):
                if capacity.unknown_reason or capacity.remaining_units <= ZERO:
                    continue
                decision = self.matcher.match(capacity.row, demand.row, at=at, allow_flexible=True)
                if not decision.compatible or decision.match_type != "size_flexible":
                    continue
                all_allocations.append(self._allocate(capacity, demand, decision))
                if demand.remaining_units <= ZERO:
                    break

        instance_results = tuple(self._coverage_result(demand) for demand in demands)
        allocated_by_reservation: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for allocation in all_allocations:
            allocated_by_reservation[allocation.reservation.id] += allocation.units
        reservation_results = tuple(
            self._utilization_result(capacity, allocated_by_reservation[capacity.row.id])
            for capacity in capacities
        )
        self._assert_invariants(instance_results, reservation_results, all_allocations)
        return CoverageAnalysis(instance_results, reservation_results, tuple(all_allocations))

    @staticmethod
    def _demand(row: AwsRdsInstance) -> InstanceDemand:
        try:
            required, method = instance_required_units(row)
            return InstanceDemand(row, required, required, method)
        except UnknownRdsConfiguration as exc:
            return InstanceDemand(row, ZERO, ZERO, "UNKNOWN", str(exc))

    @staticmethod
    def _capacity(row: AwsRdsReservedInstance, *, at: datetime) -> ReservationCapacity:
        try:
            total, method = reservation_total_units(row)
            return ReservationCapacity(row, total, total, method)
        except UnknownRdsConfiguration as exc:
            return ReservationCapacity(row, ZERO, ZERO, "UNKNOWN", str(exc))

    @staticmethod
    def _pool_key(row: AwsRdsInstance | AwsRdsReservedInstance) -> tuple[str, str, str | None]:
        return (row.region, normalize_rds_engine(row.engine_normalized), row.instance_family)

    @staticmethod
    def _demand_sort_key(demand: InstanceDemand) -> tuple[str, str, str, str, str]:
        row = demand.row
        return (
            row.account_id,
            row.region,
            row.engine_normalized,
            row.db_instance_class,
            row.db_instance_identifier,
        )

    @staticmethod
    def _capacity_sort_key(capacity: ReservationCapacity) -> tuple[str, str, str, str, str]:
        row = capacity.row
        return (
            row.account_id,
            row.region,
            row.engine_normalized,
            row.db_instance_class,
            row.reserved_db_instance_id,
        )

    @staticmethod
    def _allocate(
        capacity: ReservationCapacity, demand: InstanceDemand, decision: MatchDecision
    ) -> Allocation:
        units = min(capacity.remaining_units, demand.remaining_units)
        capacity.remaining_units -= units
        demand.remaining_units -= units
        allocation = Allocation(
            reservation=capacity.row,
            instance=demand.row,
            units=units,
            match_type=decision.match_type,
            allocation_scope=decision.allocation_scope,
            reason=decision.reason,
        )
        demand.allocations.append(allocation)
        return allocation

    @staticmethod
    def _coverage_result(demand: InstanceDemand) -> InstanceCoverageResult:
        if demand.unknown_reason:
            return InstanceCoverageResult(
                instance=demand.row,
                required_units=ZERO,
                covered_units=ZERO,
                uncovered_units=ZERO,
                coverage_percentage=ZERO,
                coverage_status=COVERAGE_UNKNOWN,
                coverage_scope=UNKNOWN_SCOPE,
                calculation_method="UNKNOWN",
                allocations=(),
                explanation={"reason": "UNKNOWN_CONFIGURATION", "detail": demand.unknown_reason},
            )
        covered = demand.required_units - demand.remaining_units
        uncovered = max(ZERO, demand.remaining_units)
        percentage = _safe_percentage(covered, demand.required_units)
        if covered <= ZERO:
            status = COVERAGE_UNCOVERED
        elif uncovered <= ZERO:
            status = COVERAGE_FULL
        else:
            status = COVERAGE_PARTIAL
        scopes = {item.allocation_scope for item in demand.allocations}
        if not scopes:
            scope = SAME_ACCOUNT
        elif CROSS_ACCOUNT_VERIFIED in scopes:
            scope = CROSS_ACCOUNT_VERIFIED
        else:
            scope = SAME_ACCOUNT
        return InstanceCoverageResult(
            instance=demand.row,
            required_units=demand.required_units,
            covered_units=covered,
            uncovered_units=uncovered,
            coverage_percentage=percentage,
            coverage_status=status,
            coverage_scope=scope,
            calculation_method=demand.calculation_method,
            allocations=tuple(demand.allocations),
            explanation={
                "topology": _instance_topology(demand.row),
                "engine": demand.row.engine_normalized,
                "family": demand.row.instance_family,
                "size": demand.row.instance_size,
                "allocation_count": len(demand.allocations),
            },
        )

    @staticmethod
    def _utilization_result(
        capacity: ReservationCapacity, allocated: Decimal
    ) -> ReservationUtilizationResult:
        if capacity.unknown_reason:
            return ReservationUtilizationResult(capacity.row, ZERO, ZERO, ZERO, ZERO)
        unused = max(ZERO, capacity.total_units - allocated)
        return ReservationUtilizationResult(
            reservation=capacity.row,
            total_units=capacity.total_units,
            allocated_units=allocated,
            unused_units=unused,
            utilization_percentage=_safe_percentage(allocated, capacity.total_units),
        )

    @staticmethod
    def _assert_invariants(
        instances: tuple[InstanceCoverageResult, ...],
        reservations: tuple[ReservationUtilizationResult, ...],
        allocations: list[Allocation],
    ) -> None:
        for result in instances:
            if result.covered_units > result.required_units:
                raise AssertionError("covered_units cannot exceed required_units")
            if result.uncovered_units < ZERO:
                raise AssertionError("uncovered_units cannot be negative")
            if not ZERO <= result.coverage_percentage <= ONE_HUNDRED:
                raise AssertionError("coverage_percentage is outside [0, 100]")
        by_reservation: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for allocation in allocations:
            by_reservation[allocation.reservation.id] += allocation.units
        for result in reservations:
            if result.allocated_units > result.total_units:
                raise AssertionError("allocated_units cannot exceed reserved_units")
            if result.unused_units < ZERO:
                raise AssertionError("unused_units cannot be negative")
            if not ZERO <= result.utilization_percentage <= ONE_HUNDRED:
                raise AssertionError("utilization_percentage is outside [0, 100]")
            if by_reservation[result.reservation.id] > result.total_units:
                raise AssertionError("sum(allocations) cannot exceed reservation capacity")
