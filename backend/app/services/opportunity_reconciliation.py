from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.cloud import CloudProvider
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_presence_history import (
    OpportunityPresenceHistory,
    OpportunityPresenceReason,
)
from app.services.collection_errors import sanitize_collection_error
from app.services.collectors import GLOBAL_COLLECTORS
from app.services.policies import list_effective_policies

ALL_REGIONS_SCOPE = "*"
logger = logging.getLogger("deepops.opportunity_reconciliation")


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
        is_global_collector = rule_key in GLOBAL_COLLECTORS
        rule_regions = [ALL_REGIONS_SCOPE] if is_global_collector else run_regions
        rule_failed_scopes = {key for key in failed_scopes if key[0] == rule_key}
        for region in rule_regions:
            key = (rule_key, region)
            # Global AWS collectors are invoked with the literal collector region
            # "global", but their successful evaluation covers findings whose logical
            # region is a concrete billing region. Persist "*" as the provider-neutral
            # all-regions coverage marker while still resolving the collector error key.
            collector_key = (rule_key, "global") if is_global_collector else key
            if collector_key in failed_scopes:
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
                    error_detail=error_details.get(collector_key),
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


def _record_presence_history(
    db: Session,
    finding: Finding,
    run: CollectionRun,
    *,
    from_status: str,
    to_status: str,
    reason: OpportunityPresenceReason,
    missing_count: int,
    missing_threshold: int | None,
    scope_execution: CollectionScopeExecution | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    event_context: dict[str, Any] = {
        "provider": finding.provider,
        "account_id": finding.account_id,
        "rule_key": finding.rule_key,
        "region": finding.region,
    }
    if scope_execution is not None:
        event_context.update(
            {
                "scope_region": scope_execution.region,
                "scope_rule_key": scope_execution.rule_key,
                "scope_status": scope_execution.status,
                "resources_examined": scope_execution.resources_examined,
            }
        )
    if context:
        event_context.update(context)

    db.add(
        OpportunityPresenceHistory(
            opportunity_id=finding.id,
            collection_run_id=run.id,
            collection_scope_execution_id=(scope_execution.id if scope_execution is not None else None),
            from_status=from_status,
            to_status=to_status,
            reason=reason.value,
            missing_count=missing_count,
            missing_threshold=missing_threshold,
            occurred_at=run.started_at,
            context=event_context,
        )
    )
    logger.info(
        "event=opportunity_presence_transition opportunity_id=%s provider=%s account=%s "
        "from_status=%s to_status=%s collection_run_id=%s missing_count=%s reason=%s",
        finding.id,
        finding.provider,
        finding.account_id,
        from_status,
        to_status,
        run.id,
        missing_count,
        reason.value,
    )


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

    previous_status = finding.presence_status
    previous_missing_count = int(finding.missing_count or 0)
    if previous_status != OpportunityPresenceStatus.ACTIVE.value:
        db = object_session(finding)
        if db is None:
            raise RuntimeError("Presence reactivation requires an attached Finding for audit history")
        _record_presence_history(
            db,
            finding,
            run,
            from_status=previous_status,
            to_status=OpportunityPresenceStatus.ACTIVE.value,
            reason=OpportunityPresenceReason.OBSERVED_AGAIN,
            missing_count=0,
            missing_threshold=None,
            context={"previous_missing_count": previous_missing_count},
        )

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

    successful_scope_rows = {
        (row.rule_key, _scope_region(row.region)): row
        for row in scope_executions
        if row.status == CollectionScopeExecutionStatus.SUCCESS.value
    }
    successful_scopes = set(successful_scope_rows)
    if not successful_scopes:
        return ReconciliationStats()

    wildcard_rule_keys = {
        rule_key for rule_key, region in successful_scopes if region == ALL_REGIONS_SCOPE
    }
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
        finding_scope = (finding.rule_key, _scope_region(finding.region))
        scope_execution = successful_scope_rows.get(finding_scope)
        if scope_execution is None and finding.rule_key in wildcard_rule_keys:
            scope_execution = successful_scope_rows.get((finding.rule_key, ALL_REGIONS_SCOPE))
        if scope_execution is None:
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
        previous_missing_count = int(finding.missing_count or 0)
        finding.missing_count = previous_missing_count + 1
        if finding.missing_since_at is None:
            finding.missing_since_at = run.started_at
        finding.presence_reconciled_run_id = run.id
        finding.presence_reconciled_at = run.started_at

        if finding.missing_count >= missing_threshold:
            finding.presence_status = OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
            finding.resolved_externally_at = run.started_at
            reason = OpportunityPresenceReason.MISSING_THRESHOLD_REACHED
            resolved_externally += 1
        else:
            finding.presence_status = OpportunityPresenceStatus.MISSING.value
            reason = OpportunityPresenceReason.NOT_OBSERVED_IN_SUCCESSFUL_SCOPE
            if previous_status == OpportunityPresenceStatus.ACTIVE.value:
                marked_missing += 1

        _record_presence_history(
            db,
            finding,
            run,
            from_status=previous_status,
            to_status=finding.presence_status,
            reason=reason,
            missing_count=finding.missing_count,
            missing_threshold=missing_threshold,
            scope_execution=scope_execution,
            context={"previous_missing_count": previous_missing_count},
        )
        reconciled += 1

    db.flush()
    return ReconciliationStats(
        opportunities_reconciled=reconciled,
        marked_missing=marked_missing,
        resolved_externally=resolved_externally,
        skipped_out_of_order=skipped_out_of_order,
    )
