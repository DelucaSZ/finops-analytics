from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_archive_history import (
    OpportunityArchiveAction,
    OpportunityArchiveHistory,
)
from app.services.audit import AuditService, new_correlation_id
from app.services.dashboard_aggregation import refresh_summaries_for_findings
from app.services.opportunity_archiving import archive_retention_locked

if TYPE_CHECKING:
    from app.models.opportunity_management_policy import OpportunityManagementPolicy

logger = logging.getLogger("deepops.opportunity_retention")

PolicyKey = Literal[
    "rejected_retention",
    "treated_retention",
    "resolved_external_retention",
    "open_retention",
]


@dataclass(frozen=True)
class RetentionPolicy:
    key: PolicyKey
    threshold_days: int
    enabled: bool


@dataclass
class OpportunityRetentionResult:
    evaluated: int = 0
    archived_total: int = 0
    archived_treated: int = 0
    archived_rejected: int = 0
    archived_resolved_externally: int = 0
    archived_open: int = 0
    skipped_needs_review: int = 0
    skipped_active_after_treatment: int = 0
    batches: int = 0
    errors: int = 0
    policy_version: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return asdict(self)


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


class OpportunityRetentionService:
    """Archive old opportunities without mutating human/technical lifecycle state."""

    def __init__(
        self,
        *,
        treated_days: int,
        rejected_days: int,
        resolved_externally_days: int,
        open_days: int = 30,
        treated_enabled: bool = True,
        rejected_enabled: bool = True,
        resolved_externally_enabled: bool = True,
        open_enabled: bool = False,
        batch_size: int = 500,
        policy_version: int | None = None,
    ) -> None:
        for name, value in (
            ("treated_days", treated_days),
            ("rejected_days", rejected_days),
            ("resolved_externally_days", resolved_externally_days),
            ("open_days", open_days),
            ("batch_size", batch_size),
        ):
            if value < 1:
                raise ValueError(f"{name} must be greater than or equal to 1")
        # Human lifecycle takes precedence over technical presence. Rejected and
        # treated are mutually exclusive, but the explicit order keeps archive
        # reasons deterministic when a technical state is also eligible.
        self.policies = (
            RetentionPolicy("rejected_retention", rejected_days, rejected_enabled),
            RetentionPolicy("treated_retention", treated_days, treated_enabled),
            RetentionPolicy(
                "resolved_external_retention",
                resolved_externally_days,
                resolved_externally_enabled,
            ),
            RetentionPolicy("open_retention", open_days, open_enabled),
        )
        self.batch_size = batch_size
        self.policy_version = policy_version

    @classmethod
    def from_settings(cls, configured: Settings = settings) -> OpportunityRetentionService:
        return cls(
            treated_days=configured.opportunity_retention_treated_days,
            rejected_days=configured.opportunity_retention_rejected_days,
            resolved_externally_days=configured.opportunity_retention_resolved_externally_days,
            treated_enabled=configured.opportunity_retention_treated_enabled,
            rejected_enabled=configured.opportunity_retention_rejected_enabled,
            resolved_externally_enabled=(
                configured.opportunity_retention_resolved_externally_enabled
            ),
            batch_size=configured.opportunity_retention_batch_size,
        )

    @classmethod
    def from_management_policy(
        cls,
        policy: OpportunityManagementPolicy,
        *,
        batch_size: int | None = None,
    ) -> OpportunityRetentionService:
        enabled = bool(policy.enabled)
        return cls(
            treated_days=policy.treated_archive_days,
            rejected_days=policy.rejected_archive_days,
            resolved_externally_days=policy.resolved_external_archive_days,
            open_days=policy.open_archive_days,
            treated_enabled=enabled and policy.treated_archive_enabled,
            rejected_enabled=enabled and policy.rejected_archive_enabled,
            resolved_externally_enabled=enabled and policy.resolved_external_archive_enabled,
            open_enabled=enabled and policy.open_archive_enabled,
            batch_size=batch_size or settings.opportunity_retention_batch_size,
            policy_version=policy.version,
        )

    @staticmethod
    def _cutoff(policy: RetentionPolicy, now: datetime) -> datetime:
        return now - timedelta(days=policy.threshold_days)

    @staticmethod
    def _expired(policy: RetentionPolicy, cutoff: datetime):
        if policy.key == "treated_retention":
            return and_(
                Finding.status == "treated",
                Finding.treated_at.is_not(None),
                Finding.treated_at <= cutoff,
            )
        if policy.key == "rejected_retention":
            return and_(
                Finding.status == "rejected",
                Finding.rejected_at.is_not(None),
                Finding.rejected_at <= cutoff,
            )
        if policy.key == "open_retention":
            return and_(
                Finding.status == "open",
                Finding.last_seen_at.is_not(None),
                Finding.last_seen_at <= cutoff,
            )
        return and_(
            Finding.presence_status == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value,
            Finding.resolved_externally_at.is_not(None),
            Finding.resolved_externally_at <= cutoff,
        )

    @staticmethod
    def _reference_timestamp(policy: RetentionPolicy, finding: Finding) -> datetime:
        if policy.key == "treated_retention":
            assert finding.treated_at is not None
            return _utc(finding.treated_at)
        if policy.key == "rejected_retention":
            assert finding.rejected_at is not None
            return _utc(finding.rejected_at)
        if policy.key == "open_retention":
            return _utc(finding.last_seen_at)
        assert finding.resolved_externally_at is not None
        return _utc(finding.resolved_externally_at)

    @staticmethod
    def _treated_activity_guard(policy: RetentionPolicy):
        if policy.key != "treated_retention":
            return True
        return or_(
            Finding.presence_status != OpportunityPresenceStatus.ACTIVE.value,
            Finding.last_seen_at.is_(None),
            Finding.treated_at.is_(None),
            Finding.last_seen_at <= Finding.treated_at,
        )

    @staticmethod
    def _recent_unarchive(cutoff: datetime):
        return exists(
            select(OpportunityArchiveHistory.id).where(
                OpportunityArchiveHistory.opportunity_id == Finding.id,
                OpportunityArchiveHistory.action == OpportunityArchiveAction.UNARCHIVE.value,
                OpportunityArchiveHistory.occurred_at > cutoff,
            )
        )

    def _eligible(self, policy: RetentionPolicy, cutoff: datetime):
        return and_(
            Finding.archived_at.is_(None),
            Finding.needs_review.is_(False),
            self._expired(policy, cutoff),
            self._treated_activity_guard(policy),
            ~self._recent_unarchive(cutoff),
        )

    def _expired_any(self, now: datetime):
        predicates = [
            self._expired(policy, self._cutoff(policy, now))
            for policy in self.policies
            if policy.enabled
        ]
        return or_(*predicates) if predicates else False

    def preview_counts(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        current = _utc(now or datetime.now(UTC))
        by_key: dict[str, int] = {}
        for policy in self.policies:
            count = 0
            if policy.enabled:
                count = int(
                    db.scalar(
                        select(func.count(Finding.id)).where(
                            self._eligible(policy, self._cutoff(policy, current))
                        )
                    )
                    or 0
                )
            by_key[policy.key] = count
        return {
            "treated_eligible": by_key.get("treated_retention", 0),
            "rejected_eligible": by_key.get("rejected_retention", 0),
            "resolved_externally_eligible": by_key.get("resolved_external_retention", 0),
            "open_eligible": by_key.get("open_retention", 0),
        }

    def _collect_preflight_counters(
        self,
        db: Session,
        *,
        now: datetime,
        result: OpportunityRetentionResult,
    ) -> None:
        expired_any = self._expired_any(now)
        if expired_any is False:
            return
        base = and_(Finding.archived_at.is_(None), expired_any)
        result.evaluated = int(
            db.scalar(select(func.count(func.distinct(Finding.id))).where(base)) or 0
        )
        result.skipped_needs_review = int(
            db.scalar(
                select(func.count(func.distinct(Finding.id))).where(
                    base,
                    Finding.needs_review.is_(True),
                )
            )
            or 0
        )
        treated_policy = next(
            (policy for policy in self.policies if policy.key == "treated_retention"), None
        )
        if treated_policy is not None and treated_policy.enabled:
            cutoff = self._cutoff(treated_policy, now)
            result.skipped_active_after_treatment = int(
                db.scalar(
                    select(func.count(func.distinct(Finding.id))).where(
                        Finding.archived_at.is_(None),
                        Finding.needs_review.is_(False),
                        self._expired(treated_policy, cutoff),
                        Finding.presence_status == OpportunityPresenceStatus.ACTIVE.value,
                        Finding.last_seen_at.is_not(None),
                        Finding.treated_at.is_not(None),
                        Finding.last_seen_at > Finding.treated_at,
                    )
                )
                or 0
            )

    def _archive_policy(
        self,
        db: Session,
        *,
        policy: RetentionPolicy,
        now: datetime,
        result: OpportunityRetentionResult,
    ) -> None:
        cutoff = self._cutoff(policy, now)
        while True:
            findings = list(
                db.scalars(
                    select(Finding)
                    .where(self._eligible(policy, cutoff))
                    .order_by(Finding.id)
                    .with_for_update(skip_locked=True)
                    .limit(self.batch_size)
                )
            )
            if not findings:
                return

            archived_findings: list[Finding] = []
            for finding in findings:
                archived = archive_retention_locked(
                    db,
                    finding,
                    archived_at=now,
                    policy=policy.key,
                    threshold_days=policy.threshold_days,
                    reference_timestamp=self._reference_timestamp(policy, finding),
                    policy_version=self.policy_version,
                    record_audit=False,
                )
                if not archived:
                    continue
                archived_findings.append(finding)
                result.archived_total += 1
                if policy.key == "treated_retention":
                    result.archived_treated += 1
                elif policy.key == "rejected_retention":
                    result.archived_rejected += 1
                elif policy.key == "resolved_external_retention":
                    result.archived_resolved_externally += 1
                else:
                    result.archived_open += 1

            if archived_findings:
                refresh_summaries_for_findings(db, archived_findings)
            db.commit()
            result.batches += 1

    def run(self, db: Session, *, now: datetime | None = None) -> OpportunityRetentionResult:
        run_at = _utc(now or datetime.now(UTC))
        result = OpportunityRetentionResult(policy_version=self.policy_version)
        self._collect_preflight_counters(db, now=run_at, result=result)
        try:
            for policy in self.policies:
                if policy.enabled:
                    self._archive_policy(db, policy=policy, now=run_at, result=result)
        except Exception:
            db.rollback()
            result.errors += 1
            logger.exception("event=opportunity_retention_batch_failed")
            raise

        if result.archived_total:
            AuditService.record(
                db,
                actor=None,
                module="opportunities",
                action="opportunity_retention.run",
                entity_type="opportunity_retention_run",
                source="SYSTEM",
                metadata=result.as_dict(),
                correlation_id=new_correlation_id(),
            )
            db.commit()

        logger.info(
            "event=opportunity_retention_run policy_version=%s evaluated=%s archived=%s "
            "treated=%s rejected=%s resolved_externally=%s open=%s "
            "skipped_needs_review=%s skipped_active_after_treatment=%s batches=%s errors=%s",
            self.policy_version,
            result.evaluated,
            result.archived_total,
            result.archived_treated,
            result.archived_rejected,
            result.archived_resolved_externally,
            result.archived_open,
            result.skipped_needs_review,
            result.skipped_active_after_treatment,
            result.batches,
            result.errors,
        )
        return result
