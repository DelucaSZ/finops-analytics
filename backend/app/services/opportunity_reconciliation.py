from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_observation import OpportunityObservation
from app.services.collection_errors import sanitize_collection_error
from app.services.collectors import GLOBAL_COLLECTORS
from app.services.policies import list_effective_policies


@dataclass(frozen=True)
class ReconciliationStats:
    opportunities_reconciled: int = 0
    marked_missing: int = 0
    resolved_externally: int = 0
    skipped_out_of_order: int = 0


def _normalized_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _scope_region(value: str | None) -> str:
    return value or "global"


def _regions(run: CollectionRun) -> list[str]:
    values = run.scope.get("regions", []) if isinstance(run.scope, dict) else []
    rendered = sorted({_scope_region(str(value)) for value in values if value})
    return rendered or ["global"]


def _observed_services(result: Any) -> dict[tuple[str, str], str | None]:
    services: dict[tuple[str, str], set[str]] = {}
    for finding in list(getattr(result, "findings", []) or []):
        key = (str(finding.rule_key), _scope_region(finding.region))
        services.setdefault(key, set()).add(str(finding.service))
    return {
        key: next(iter(values)) if len(values) == 1 else None for key, values in services.items()
    }


def _aws_error_scopes(
    errors: list[object],
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], str]]:
    failed: set[tuple[str, str]] = set()
    details: dict[tuple[str, str], str] = {}
    for raw in errors:
        text = str(raw)
        prefix, separator, _ = text.partition(":")
        rule_key, marker, region = prefix.rpartition("@")
        if not separator or not marker or not rule_key or not region:
            continue
        key = (rule_key, _scope_region(region))
        failed.add(key)
        details[key] = (sanitize_collection_error(raw) or "Collector scope failed")[:4000]
    return failed, details


def _aws_scope_rows(
    db: Session,
    cloud_account: CloudAccount,
    run: CollectionRun,
    result: Any,
    *,
    finished_at: datetime,
) -> list[CollectionScopeExecution]:
    configuration = cloud_account.aws_configuration
    if configuration is None:
        return []
    policies = list_effective_policies(db, configuration.id)
    configured_rule_keys = [
        str(policy["rule_key"])
        for policy in policies
        if policy["enabled"] and policy["implemented"]
    ]
    successful_rule_keys = set(getattr(result, "active_rule_keys", []) or [])
    errors = list(getattr(result, "collector_errors", []) or [])
    failed_scopes, error_details = _aws_error_scopes(errors)
    services = _observed_services(result)
    run_regions = _regions(run)
    rows: list[CollectionScopeExecution] = []

    for rule_key in sorted(set(configured_rule_keys)):
        rule_regions = ["global"] if rule_key in GLOBAL_COLLECTORS else run_regions
        rule_failed_scopes = {key for key in failed_scopes if key[0] == rule_key}
        for region in rule_regions:
            key = (rule_key, region)
            if key in failed_scopes:
                status = CollectionScopeExecutionStatus.FAILED.value
            elif rule_key in successful_rule_keys or rule_failed_scopes:
                # run_collectors executes every configured region. If a rule has a
                # structured failure in one region, regions without that failure returned
                # normally and therefore provide valid zero-result coverage.
                status = CollectionScopeExecutionStatus.SUCCESS.value
            else:
                # Conservative fallback for an unexpected contract mismatch.
                status = CollectionScopeExecutionStatus.SKIPPED.value
            rows.append(
                CollectionScopeExecution(
                    collection_run_id=run.id,
                    provider=run.provider,
                    account_id=run.account_id,
                    region=region,
                    service=services.get(key),
                    rule_key=rule_key,
                    status=status,
                    started_at=run.started_at,
                    finished_at=finished_at,
                    resources_examined=None,
                    error_detail=error_details.get(key),
                )
            )
    return rows


def _oci_scope_rows(
    run: CollectionRun,
    result: Any,
    *,
    finished_at: datetime,
) -> list[CollectionScopeExecution]:
    rule_keys = sorted(set(getattr(result, "active_rule_keys", []) or []))
    errors = list(getattr(result, "collector_errors", []) or [])
    services = _observed_services(result)
    rows: list[CollectionScopeExecution] = []
    for rule_key in rule_keys:
        for region in _regions(run):
            key = (rule_key, region)
            # OCI currently exposes partial source issues at pipeline level, not enough
            # rule/region detail to prove absence safely. Any issue therefore makes the
            # analyzer scope non-authoritative for absence while preserving observations.
            status = (
                CollectionScopeExecutionStatus.SUCCESS.value
                if not errors
                else CollectionScopeExecutionStatus.SKIPPED.value
            )
            rows.append(
                CollectionScopeExecution(
                    collection_run_id=run.id,
                    provider=run.provider,
                    account_id=run.account_id,
                    region=region,
                    service=services.get(key),
                    rule_key=rule_key,
                    status=status,
                    started_at=run.started_at,
                    finished_at=finished_at,
                    resources_examined=(
                        getattr(result, "resources_analyzed", None) if not errors else None
                    ),
                    error_detail=(
                        None
                        if not errors
                        else "OCI partial coverage; absence reconciliation skipped"
                    ),
                )
            )
    return rows


def build_collection_scope_executions(
    db: Session,
    cloud_account: CloudAccount,
    run: CollectionRun,
    result: Any,
    *,
    finished_at: datetime,
) -> list[CollectionScopeExecution]:
    """Build conservative, provider-adapted coverage rows for the completed provider I/O."""

    if run.provider == CloudProvider.AWS.value:
        return _aws_scope_rows(db, cloud_account, run, result, finished_at=finished_at)
    if run.provider == CloudProvider.OCI.value:
        return _oci_scope_rows(run, result, finished_at=finished_at)
    return []


def persist_collection_scope_executions(
    db: Session,
    run: CollectionRun,
    rows: list[CollectionScopeExecution],
) -> list[CollectionScopeExecution]:
    existing = {
        (row.region, row.rule_key): row
        for row in db.scalars(
            select(CollectionScopeExecution)
            .where(CollectionScopeExecution.collection_run_id == run.id)
            .with_for_update()
        )
    }
    persisted: list[CollectionScopeExecution] = []
    for candidate in rows:
        key = (candidate.region, candidate.rule_key)
        row = existing.get(key)
        if row is None:
            db.add(candidate)
            existing[key] = candidate
            persisted.append(candidate)
            continue
        row.provider = candidate.provider
        row.account_id = candidate.account_id
        row.service = candidate.service
        row.status = candidate.status
        row.started_at = candidate.started_at
        row.finished_at = candidate.finished_at
        row.resources_examined = candidate.resources_examined
        row.error_detail = candidate.error_detail
        persisted.append(row)
    db.flush()
    return persisted


def reactivate_presence_from_observation(
    finding: Finding,
    run: CollectionRun,
) -> bool:
    """Reactivate current presence only when the observing run is not older than current state."""

    run_started_at = _normalized_utc(run.started_at)
    if finding.presence_reconciled_at is not None:
        reconciled_at = _normalized_utc(finding.presence_reconciled_at)
        if run_started_at < reconciled_at:
            return False
    finding.presence_status = OpportunityPresenceStatus.ACTIVE.value
    finding.missing_count = 0
    finding.missing_since_at = None
    finding.resolved_externally_at = None
    finding.presence_reconciled_run_id = run.id
    finding.presence_reconciled_at = run.started_at
    return True


def reconcile_opportunity_presence(
    db: Session,
    run: CollectionRun,
    scope_executions: list[CollectionScopeExecution],
    *,
    missing_threshold: int,
) -> ReconciliationStats:
    """Apply absence only inside scopes proven SUCCESS for this collection run."""

    if missing_threshold < 1:
        raise ValueError("missing_threshold must be greater than or equal to 1")
    if run.status == CollectionRunStatus.FAILED:
        return ReconciliationStats()

    successful_scopes = {
        (row.rule_key, _scope_region(row.region))
        for row in scope_executions
        if row.status == CollectionScopeExecutionStatus.SUCCESS.value
    }
    if not successful_scopes:
        return ReconciliationStats()

    observed_ids = set(
        db.scalars(
            select(OpportunityObservation.opportunity_id).where(
                OpportunityObservation.collection_run_id == run.id
            )
        )
    )
    rule_keys = {rule_key for rule_key, _ in successful_scopes}
    findings = list(
        db.scalars(
            select(Finding)
            .where(
                Finding.provider == run.provider,
                Finding.account_id == run.account_id,
                Finding.rule_key.in_(rule_keys),
                Finding.presence_status.in_(
                    [
                        OpportunityPresenceStatus.ACTIVE.value,
                        OpportunityPresenceStatus.MISSING.value,
                    ]
                ),
            )
            .with_for_update()
        )
    )

    reconciled = 0
    marked_missing = 0
    resolved_externally = 0
    skipped_out_of_order = 0
    run_started_at = _normalized_utc(run.started_at)

    for finding in findings:
        if (finding.rule_key, _scope_region(finding.region)) not in successful_scopes:
            continue
        if finding.id in observed_ids:
            continue
        if finding.presence_reconciled_run_id == run.id:
            continue
        if finding.presence_reconciled_at is not None and run_started_at <= _normalized_utc(
            finding.presence_reconciled_at
        ):
            skipped_out_of_order += 1
            continue
        if finding.last_seen_at is not None and run_started_at < _normalized_utc(
            finding.last_seen_at
        ):
            skipped_out_of_order += 1
            continue

        previous_status = finding.presence_status
        finding.missing_count = int(finding.missing_count or 0) + 1
        if finding.missing_since_at is None:
            finding.missing_since_at = run.started_at
        finding.presence_reconciled_run_id = run.id
        finding.presence_reconciled_at = run.started_at

        if finding.missing_count >= missing_threshold:
            finding.presence_status = OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
            finding.resolved_externally_at = run.started_at
            resolved_externally += 1
        else:
            finding.presence_status = OpportunityPresenceStatus.MISSING.value
            if previous_status == OpportunityPresenceStatus.ACTIVE.value:
                marked_missing += 1
        reconciled += 1

    db.flush()
    return ReconciliationStats(
        opportunities_reconciled=reconciled,
        marked_missing=marked_missing,
        resolved_externally=resolved_externally,
        skipped_out_of_order=skipped_out_of_order,
    )
