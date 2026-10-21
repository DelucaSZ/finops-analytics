from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.opportunity_history_cycle import (
    OpportunityHistoryCycle,
    OpportunityHistoryCycleStatus,
)
from app.models.opportunity_management_policy import (
    OpportunityCycleMode,
    OpportunityMaintenanceState,
    OpportunityManagementPolicy,
)
from app.models.user import User
from app.schemas.opportunity_policy import (
    OpportunityPolicyFields,
    OpportunityPolicyPreviewRequest,
    OpportunityPolicyUpdate,
)
from app.services.audit import AuditService, audit_snapshot, new_correlation_id
from app.services.opportunity_history import OpportunityHistoryCycleService
from app.services.retention import retention_cutoff, retention_preview

logger = logging.getLogger("deepops.opportunity_policy")

GLOBAL_SCOPE = "GLOBAL"


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _setting_explicit(configured: Settings, field_name: str, env_name: str) -> bool:
    # model_fields_set includes values loaded from environment and .env sources.
    # os.environ is kept as defense in depth for custom Settings source behavior.
    return (
        field_name in configured.model_fields_set
        or (env_name in os.environ and os.environ[env_name].strip() != "")
    )


def _policy_values(policy: OpportunityManagementPolicy) -> dict[str, Any]:
    return {
        "cycle_mode": policy.cycle_mode,
        "cycle_length_days": policy.cycle_length_days,
        "cycle_timezone": policy.cycle_timezone,
        "cycle_anchor_date": policy.cycle_anchor_date,
        "automatic_cycle_close_enabled": policy.automatic_cycle_close_enabled,
        "treated_archive_enabled": policy.treated_archive_enabled,
        "treated_archive_days": policy.treated_archive_days,
        "rejected_archive_enabled": policy.rejected_archive_enabled,
        "rejected_archive_days": policy.rejected_archive_days,
        "resolved_external_archive_enabled": policy.resolved_external_archive_enabled,
        "resolved_external_archive_days": policy.resolved_external_archive_days,
        "open_archive_enabled": policy.open_archive_enabled,
        "open_archive_days": policy.open_archive_days,
        "observation_retention_days": policy.observation_retention_days,
        "enabled": policy.enabled,
    }


def policy_snapshot(policy: OpportunityManagementPolicy) -> dict[str, Any]:
    return {
        "policy_version": policy.version,
        "cycle_mode": policy.cycle_mode,
        "cycle_length_days": policy.cycle_length_days,
        "timezone": policy.cycle_timezone,
        "anchor_date": (
            policy.cycle_anchor_date.isoformat() if policy.cycle_anchor_date is not None else None
        ),
    }


class OpportunityManagementPolicyService:
    @staticmethod
    def bootstrap_values(configured: Settings = settings) -> dict[str, Any]:
        """Use legacy envs only as first-row bootstrap; UI persistence wins afterwards."""

        today = datetime.now(UTC).date()
        return {
            "scope": GLOBAL_SCOPE,
            "cycle_mode": OpportunityCycleMode.CALENDAR_MONTH.value,
            "cycle_length_days": 30,
            "cycle_timezone": "UTC",
            "cycle_anchor_date": date(today.year, today.month, 1),
            "automatic_cycle_close_enabled": False,
            "treated_archive_enabled": (
                configured.opportunity_retention_treated_enabled
                if _setting_explicit(
                    configured,
                    "opportunity_retention_treated_enabled",
                    "OPPORTUNITY_RETENTION_TREATED_ENABLED",
                )
                else True
            ),
            "treated_archive_days": (
                configured.opportunity_retention_treated_days
                if _setting_explicit(
                    configured,
                    "opportunity_retention_treated_days",
                    "OPPORTUNITY_RETENTION_TREATED_DAYS",
                )
                else 30
            ),
            "rejected_archive_enabled": (
                configured.opportunity_retention_rejected_enabled
                if _setting_explicit(
                    configured,
                    "opportunity_retention_rejected_enabled",
                    "OPPORTUNITY_RETENTION_REJECTED_ENABLED",
                )
                else True
            ),
            "rejected_archive_days": (
                configured.opportunity_retention_rejected_days
                if _setting_explicit(
                    configured,
                    "opportunity_retention_rejected_days",
                    "OPPORTUNITY_RETENTION_REJECTED_DAYS",
                )
                else 30
            ),
            "resolved_external_archive_enabled": (
                configured.opportunity_retention_resolved_externally_enabled
                if _setting_explicit(
                    configured,
                    "opportunity_retention_resolved_externally_enabled",
                    "OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_ENABLED",
                )
                else True
            ),
            "resolved_external_archive_days": (
                configured.opportunity_retention_resolved_externally_days
                if _setting_explicit(
                    configured,
                    "opportunity_retention_resolved_externally_days",
                    "OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_DAYS",
                )
                else 30
            ),
            "open_archive_enabled": False,
            "open_archive_days": 30,
            "observation_retention_days": (
                max(31, configured.opportunity_observation_retention_days)
                if _setting_explicit(
                    configured,
                    "opportunity_observation_retention_days",
                    "NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS",
                )
                else 400
            ),
            "enabled": (
                configured.opportunity_retention_enabled
                if _setting_explicit(
                    configured,
                    "opportunity_retention_enabled",
                    "OPPORTUNITY_RETENTION_ENABLED",
                )
                else True
            ),
            "version": 1,
        }

    @staticmethod
    def _adopt_legacy_open_cycles(
        db: Session,
        policy: OpportunityManagementPolicy,
    ) -> None:
        legacy_open = list(
            db.scalars(
                select(OpportunityHistoryCycle).where(
                    OpportunityHistoryCycle.status == OpportunityHistoryCycleStatus.OPEN.value,
                    OpportunityHistoryCycle.policy_version.is_(None),
                )
            )
        )
        for cycle in legacy_open:
            cycle.policy_version = policy.version
            metadata = dict(cycle.metadata_json or {})
            metadata.setdefault("policy", policy_snapshot(policy))
            cycle.metadata_json = metadata
        if legacy_open:
            db.flush()

    @classmethod
    def get_or_create(
        cls,
        db: Session,
        *,
        configured: Settings = settings,
    ) -> OpportunityManagementPolicy:
        policy = db.scalar(
            select(OpportunityManagementPolicy).where(
                OpportunityManagementPolicy.scope == GLOBAL_SCOPE
            )
        )
        if policy is not None:
            return policy

        try:
            with db.begin_nested():
                policy = OpportunityManagementPolicy(**cls.bootstrap_values(configured))
                db.add(policy)
                db.flush()
                cls._adopt_legacy_open_cycles(db, policy)
            return policy
        except IntegrityError:
            policy = db.scalar(
                select(OpportunityManagementPolicy).where(
                    OpportunityManagementPolicy.scope == GLOBAL_SCOPE
                )
            )
            if policy is None:
                raise
            return policy

    @staticmethod
    def get_maintenance_state(db: Session) -> OpportunityMaintenanceState:
        state = db.get(OpportunityMaintenanceState, 1)
        if state is None:
            state = OpportunityMaintenanceState(id=1)
            db.add(state)
            db.flush()
        return state

    @staticmethod
    def _calendar_bounds(
        timestamp: datetime,
        timezone: str,
    ) -> tuple[datetime, datetime, str]:
        tz = ZoneInfo(timezone)
        local = _utc(timestamp).astimezone(tz)
        start_local = datetime(local.year, local.month, 1, tzinfo=tz)
        if local.month == 12:
            end_local = datetime(local.year + 1, 1, 1, tzinfo=tz)
        else:
            end_local = datetime(local.year, local.month + 1, 1, tzinfo=tz)
        return (
            start_local.astimezone(UTC),
            end_local.astimezone(UTC),
            f"{start_local.month:02d}/{start_local.year}",
        )

    @staticmethod
    def _fixed_bounds(
        timestamp: datetime,
        *,
        timezone: str,
        anchor: date,
        length_days: int,
    ) -> tuple[datetime, datetime, str]:
        tz = ZoneInfo(timezone)
        local = _utc(timestamp).astimezone(tz)
        days_from_anchor = (local.date() - anchor).days
        index = days_from_anchor // length_days
        start_date = anchor + timedelta(days=index * length_days)
        end_date = start_date + timedelta(days=length_days)
        start_local = datetime.combine(start_date, time.min, tzinfo=tz)
        end_local = datetime.combine(end_date, time.min, tzinfo=tz)
        return (
            start_local.astimezone(UTC),
            end_local.astimezone(UTC),
            f"{start_date.isoformat()} · {length_days} dias",
        )

    @classmethod
    def cycle_bounds(
        cls,
        policy: OpportunityManagementPolicy | OpportunityPolicyFields,
        timestamp: datetime,
    ) -> tuple[datetime, datetime, str]:
        if policy.cycle_mode == OpportunityCycleMode.CALENDAR_MONTH.value:
            return cls._calendar_bounds(timestamp, policy.cycle_timezone)
        if policy.cycle_anchor_date is None:
            raise ValueError("FIXED_DAYS requires cycle_anchor_date")
        return cls._fixed_bounds(
            timestamp,
            timezone=policy.cycle_timezone,
            anchor=policy.cycle_anchor_date,
            length_days=policy.cycle_length_days,
        )

    @staticmethod
    def _cycle_policy_metadata(policy: OpportunityManagementPolicy) -> dict[str, Any]:
        return {"policy": policy_snapshot(policy)}

    @classmethod
    def get_or_create_cycle_for(
        cls,
        db: Session,
        timestamp: datetime,
        *,
        policy: OpportunityManagementPolicy | None = None,
    ) -> OpportunityHistoryCycle:
        current = _utc(timestamp)
        existing = db.scalar(
            select(OpportunityHistoryCycle)
            .where(
                OpportunityHistoryCycle.period_start <= current,
                OpportunityHistoryCycle.period_end > current,
            )
            .order_by(OpportunityHistoryCycle.period_start.desc())
        )
        if existing is not None:
            return existing

        active_policy = policy or cls.get_or_create(db)
        start, end, label = cls.cycle_bounds(active_policy, current)
        exact = db.scalar(
            select(OpportunityHistoryCycle).where(
                OpportunityHistoryCycle.period_start == start,
                OpportunityHistoryCycle.period_end == end,
            )
        )
        if exact is not None:
            return exact

        cycle = OpportunityHistoryCycleService.create_cycle(
            db,
            period_start=start,
            period_end=end,
            label=label,
            timezone=active_policy.cycle_timezone,
        )
        cycle.policy_version = active_policy.version
        cycle.metadata_json = cls._cycle_policy_metadata(active_policy)
        db.flush()
        return cycle

    @classmethod
    def ensure_next_cycle(
        cls,
        db: Session,
        previous: OpportunityHistoryCycle,
        *,
        policy: OpportunityManagementPolicy | None = None,
    ) -> OpportunityHistoryCycle:
        existing = db.scalar(
            select(OpportunityHistoryCycle).where(
                OpportunityHistoryCycle.period_start == previous.period_end
            )
        )
        if existing is not None:
            return existing

        active_policy = policy or cls.get_or_create(db)
        start = _utc(previous.period_end)
        tz = ZoneInfo(active_policy.cycle_timezone)
        local_start = start.astimezone(tz)

        if active_policy.cycle_mode == OpportunityCycleMode.CALENDAR_MONTH.value:
            if local_start.month == 12:
                next_boundary = datetime(local_start.year + 1, 1, 1, tzinfo=tz)
            else:
                next_boundary = datetime(
                    local_start.year, local_start.month + 1, 1, tzinfo=tz
                )
            if next_boundary <= local_start:
                if next_boundary.month == 12:
                    next_boundary = datetime(next_boundary.year + 1, 1, 1, tzinfo=tz)
                else:
                    next_boundary = datetime(
                        next_boundary.year, next_boundary.month + 1, 1, tzinfo=tz
                    )
            end = next_boundary.astimezone(UTC)
            label = f"{local_start.month:02d}/{local_start.year}"
        else:
            end = (local_start + timedelta(days=active_policy.cycle_length_days)).astimezone(UTC)
            label = (
                f"{local_start.date().isoformat()} · "
                f"{active_policy.cycle_length_days} dias"
            )

        cycle = OpportunityHistoryCycleService.create_cycle(
            db,
            period_start=start,
            period_end=end,
            label=label,
            timezone=active_policy.cycle_timezone,
        )
        cycle.policy_version = active_policy.version
        cycle.metadata_json = cls._cycle_policy_metadata(active_policy)
        db.flush()
        return cycle

    @classmethod
    def update(
        cls,
        db: Session,
        payload: OpportunityPolicyUpdate,
        *,
        actor: User,
    ) -> OpportunityManagementPolicy:
        policy = db.scalar(
            select(OpportunityManagementPolicy)
            .where(OpportunityManagementPolicy.scope == GLOBAL_SCOPE)
            .with_for_update()
        )
        if policy is None:
            policy = cls.get_or_create(db)
            db.flush()

        if policy.version != payload.expected_version:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A configuração foi alterada por outro administrador. "
                    "Recarregue os valores antes de salvar novamente."
                ),
            )

        before = audit_snapshot(_policy_values(policy) | {"version": policy.version})
        values = payload.model_dump(exclude={"expected_version"})
        for field, value in values.items():
            setattr(policy, field, value)
        policy.version += 1
        policy.updated_by = actor.id
        db.flush()
        after = audit_snapshot(_policy_values(policy) | {"version": policy.version})

        AuditService.record(
            db,
            actor=actor,
            module="opportunities",
            action="opportunity_policy.update",
            entity_type="opportunity_management_policy",
            entity_id=policy.id,
            entity_label="Política global de oportunidades",
            before=before,
            after=after,
            source="API",
            metadata={"policy_version": policy.version},
            correlation_id=new_correlation_id(),
        )
        db.flush()
        return policy

    @classmethod
    def preview(
        cls,
        db: Session,
        candidate: OpportunityPolicyPreviewRequest,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _utc(now or datetime.now(UTC))
        from app.services.opportunity_retention import OpportunityRetentionService

        retention = OpportunityRetentionService(
            treated_days=candidate.treated_archive_days,
            rejected_days=candidate.rejected_archive_days,
            resolved_externally_days=candidate.resolved_external_archive_days,
            open_days=candidate.open_archive_days,
            treated_enabled=candidate.enabled and candidate.treated_archive_enabled,
            rejected_enabled=candidate.enabled and candidate.rejected_archive_enabled,
            resolved_externally_enabled=(
                candidate.enabled and candidate.resolved_external_archive_enabled
            ),
            open_enabled=candidate.enabled and candidate.open_archive_enabled,
            batch_size=settings.opportunity_retention_batch_size,
        )
        counts = retention.preview_counts(db, now=current)
        observation = retention_preview(
            db,
            cutoff=retention_cutoff(days=candidate.observation_retention_days, now=current),
        )

        overdue = int(
            db.scalar(
                select(func.count(OpportunityHistoryCycle.id)).where(
                    OpportunityHistoryCycle.status
                    == OpportunityHistoryCycleStatus.OPEN.value,
                    OpportunityHistoryCycle.period_end <= current,
                )
            )
            or 0
        )
        existing_policy = db.scalar(
            select(OpportunityManagementPolicy).where(
                OpportunityManagementPolicy.scope == GLOBAL_SCOPE
            )
        )
        if existing_policy is None:
            existing_policy = OpportunityManagementPolicy(**cls.bootstrap_values())
        warnings: list[str] = []
        if candidate.observation_retention_days < existing_policy.observation_retention_days:
            warnings.append(
                "A redução da retenção tornará observações antigas elegíveis para remoção "
                "na próxima execução. Snapshots fechados não serão removidos."
            )
        if any(
            (
                candidate.treated_archive_days < existing_policy.treated_archive_days,
                candidate.rejected_archive_days < existing_policy.rejected_archive_days,
                candidate.resolved_external_archive_days
                < existing_policy.resolved_external_archive_days,
                candidate.open_archive_days < existing_policy.open_archive_days
                and candidate.open_archive_enabled,
            )
        ):
            warnings.append(
                "A redução dos prazos de arquivamento pode mover mais oportunidades para "
                "o Histórico na próxima execução de retenção."
            )
        if candidate.automatic_cycle_close_enabled and overdue:
            warnings.append(
                f"{overdue} ciclo(s) vencido(s) será(ão) avaliado(s) para fechamento "
                "na próxima execução automática."
            )

        cycle = db.scalar(
            select(OpportunityHistoryCycle)
            .where(
                OpportunityHistoryCycle.period_start <= current,
                OpportunityHistoryCycle.period_end > current,
            )
            .order_by(OpportunityHistoryCycle.period_start.desc())
        )
        return {
            **counts,
            "observations_eligible_for_purge": observation.eligible_observations,
            "overdue_cycles_awaiting_close": overdue,
            "current_cycle": cls.cycle_summary(cycle) if cycle is not None else None,
            "warnings": warnings,
        }

    @staticmethod
    def cycle_summary(cycle: OpportunityHistoryCycle) -> dict[str, Any]:
        return {
            "id": cycle.id,
            "label": cycle.label,
            "period_start": cycle.period_start,
            "period_end": cycle.period_end,
            "status": cycle.status,
            "timezone": cycle.timezone,
            "policy_version": cycle.policy_version,
        }

    @classmethod
    def auto_close_due_cycles(
        cls,
        db: Session,
        *,
        policy: OpportunityManagementPolicy | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        active_policy = policy or cls.get_or_create(db)
        current = _utc(now or datetime.now(UTC))
        result = {"evaluated": 0, "closed": 0, "deferred_running": 0}
        if not active_policy.enabled or not active_policy.automatic_cycle_close_enabled:
            return result

        due = list(
            db.scalars(
                select(OpportunityHistoryCycle)
                .where(
                    OpportunityHistoryCycle.status
                    == OpportunityHistoryCycleStatus.OPEN.value,
                    OpportunityHistoryCycle.period_end <= current,
                )
                .order_by(OpportunityHistoryCycle.period_end)
                .with_for_update(skip_locked=True)
            )
        )
        for cycle in due:
            result["evaluated"] += 1
            coverage = OpportunityHistoryCycleService.collection_coverage(db, cycle)
            if coverage["running"]:
                result["deferred_running"] += 1
                logger.info(
                    "event=cycle_close_deferred cycle_id=%s policy_version=%s running=%s",
                    cycle.id,
                    active_policy.version,
                    coverage["running"],
                )
                continue

            OpportunityHistoryCycleService.close_cycle(
                db,
                cycle.id,
                actor=None,
                close_reason="SCHEDULED",
            )
            cls.ensure_next_cycle(db, cycle, policy=active_policy)
            result["closed"] += 1

        if result["closed"]:
            AuditService.record(
                db,
                actor=None,
                module="opportunities",
                action="opportunity_cycle.auto_close",
                entity_type="opportunity_history_cycle",
                entity_id=None,
                entity_label="Fechamento automático de ciclos",
                source="SYSTEM",
                metadata={
                    "policy_version": active_policy.version,
                    **result,
                },
                correlation_id=new_correlation_id(),
            )
        db.flush()
        return result

    @classmethod
    def read_payload(
        cls,
        db: Session,
        policy: OpportunityManagementPolicy,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _utc(now or datetime.now(UTC))
        cycle = cls.get_or_create_cycle_for(db, current, policy=policy)
        state = cls.get_maintenance_state(db)
        return {
            "id": policy.id,
            **_policy_values(policy),
            "version": policy.version,
            "updated_at": policy.updated_at,
            "updated_by": policy.updated_by,
            "current_cycle": cls.cycle_summary(cycle),
            "next_cycle_start": cycle.period_end,
            "maintenance": {
                "last_retention_run_at": state.last_retention_run_at,
                "last_cycle_close_check_at": state.last_cycle_close_check_at,
                "last_observation_cleanup_at": state.last_observation_cleanup_at,
            },
        }
