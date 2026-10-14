from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cloud import normalize_provider
from app.models.account import CloudAccount
from app.models.finding import Finding
from app.models.finops_ledger import (
    FinOpsLedgerDirection,
    FinOpsLedgerEntry,
    FinOpsLedgerEntryType,
    FinOpsLedgerPeriodicity,
    FinOpsLedgerSource,
)
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.finops_ledger import FinOpsLedgerError, FinOpsLedgerService

logger = logging.getLogger(__name__)

NO_MONETARY_SAVING = "NO_MONETARY_SAVING"
ZERO_SAVING = "ZERO_SAVING"
NEGATIVE_SAVING = "NEGATIVE_SAVING"
NO_CURRENCY = "NO_CURRENCY"
INVALID_CURRENCY = "INVALID_CURRENCY"
NO_NEW_FINANCIAL_EVENT = "NO_NEW_FINANCIAL_EVENT"
CREATED = "CREATED"


@dataclass(frozen=True)
class OpportunitySavingRecognitionResult:
    entry: FinOpsLedgerEntry | None
    reason: str
    observation_id: str | None = None

    @property
    def created(self) -> bool:
        return self.entry is not None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


class OpportunitySavingRecognitionService:
    """Recognize monthly opportunity savings at explicit human treatment events."""

    def __init__(self, db: Session):
        self.db = db
        self.ledger = FinOpsLedgerService(db)

    def _latest_observations(
        self, opportunity_ids: list[str]
    ) -> dict[str, OpportunityObservation]:
        if not opportunity_ids:
            return {}
        rows = self.db.scalars(
            select(OpportunityObservation)
            .where(OpportunityObservation.opportunity_id.in_(opportunity_ids))
            .order_by(
                OpportunityObservation.opportunity_id,
                OpportunityObservation.observed_at.desc(),
                OpportunityObservation.id.desc(),
            )
        ).all()
        latest: dict[str, OpportunityObservation] = {}
        for row in rows:
            latest.setdefault(row.opportunity_id, row)
        return latest

    def _previous_cycle_events(
        self,
        candidates: list[tuple[Finding, OpportunityStatusHistory]],
    ) -> dict[str, OpportunityStatusHistory]:
        opportunity_ids = [finding.id for finding, _event in candidates]
        if not opportunity_ids:
            return {}
        current_event_ids = {finding.id: event.id for finding, event in candidates}
        treatment_rows = self.db.scalars(
            select(OpportunityStatusHistory)
            .where(
                OpportunityStatusHistory.opportunity_id.in_(opportunity_ids),
                OpportunityStatusHistory.action == "treat",
                OpportunityStatusHistory.to_status == "treated",
            )
            .order_by(
                OpportunityStatusHistory.opportunity_id,
                OpportunityStatusHistory.changed_at.desc(),
                OpportunityStatusHistory.id.desc(),
            )
        ).all()
        previous: dict[str, OpportunityStatusHistory] = {}
        for row in treatment_rows:
            if row.id == current_event_ids.get(row.opportunity_id):
                continue
            previous.setdefault(row.opportunity_id, row)

        # A legacy treated finding can have no historical treat event. A later reopen
        # still proves there was an earlier treatment, so use that reopen only as a
        # conservative fallback baseline. This prevents retroactive credit without
        # inventing a timestamp for the legacy treatment.
        legacy_ids = [
            opportunity_id
            for opportunity_id in opportunity_ids
            if opportunity_id not in previous
        ]
        if legacy_ids:
            reopen_rows = self.db.scalars(
                select(OpportunityStatusHistory)
                .where(
                    OpportunityStatusHistory.opportunity_id.in_(legacy_ids),
                    OpportunityStatusHistory.action == "reopen",
                    OpportunityStatusHistory.from_status == "treated",
                    OpportunityStatusHistory.to_status == "open",
                )
                .order_by(
                    OpportunityStatusHistory.opportunity_id,
                    OpportunityStatusHistory.changed_at.desc(),
                    OpportunityStatusHistory.id.desc(),
                )
            ).all()
            for row in reopen_rows:
                previous.setdefault(row.opportunity_id, row)
        return previous

    def _cloud_accounts(self, findings: list[Finding]) -> dict[tuple[str, str], CloudAccount]:
        if not findings:
            return {}
        providers = {normalize_provider(finding.provider) for finding in findings}
        account_ids = {finding.account_id for finding in findings}
        rows = self.db.scalars(
            select(CloudAccount).where(
                CloudAccount.provider.in_(providers),
                CloudAccount.native_account_id.in_(account_ids),
            )
        ).all()
        return {(account.provider, account.native_account_id): account for account in rows}

    @staticmethod
    def _validate_treatment_event(
        finding: Finding,
        event: OpportunityStatusHistory,
        actor: User,
    ) -> None:
        if (
            event.opportunity_id != finding.id
            or event.from_status != "open"
            or event.to_status != "treated"
            or event.action != "treat"
            or event.changed_by != actor.id
        ):
            raise FinOpsLedgerError("Invalid human treatment event for saving recognition")

    @staticmethod
    def _skip(
        finding: Finding,
        event: OpportunityStatusHistory,
        reason: str,
        observation: OpportunityObservation | None,
    ) -> OpportunitySavingRecognitionResult:
        logger.info(
            "event=saving_recognition_skipped finding_id=%s treatment_event_id=%s "
            "provider=%s reason=%s",
            finding.id,
            event.id,
            finding.provider,
            reason.lower(),
        )
        return OpportunitySavingRecognitionResult(
            entry=None,
            reason=reason,
            observation_id=observation.id if observation is not None else None,
        )

    def recognize_many(
        self,
        candidates: list[tuple[Finding, OpportunityStatusHistory]],
        actor: User,
    ) -> list[OpportunitySavingRecognitionResult]:
        if not candidates:
            return []

        for finding, event in candidates:
            self._validate_treatment_event(finding, event, actor)

        opportunity_ids = [finding.id for finding, _event in candidates]
        latest_observations = self._latest_observations(opportunity_ids)
        previous_cycles = self._previous_cycle_events(candidates)
        cloud_accounts = self._cloud_accounts([finding for finding, _event in candidates])

        results: list[OpportunitySavingRecognitionResult] = []
        for finding, event in candidates:
            observation = latest_observations.get(finding.id)
            previous_cycle = previous_cycles.get(finding.id)
            if previous_cycle is not None and (
                observation is None
                or _aware(observation.observed_at) <= _aware(previous_cycle.changed_at)
            ):
                results.append(
                    self._skip(
                        finding,
                        event,
                        NO_NEW_FINANCIAL_EVENT,
                        observation,
                    )
                )
                continue

            snapshot = observation if observation is not None else finding
            amount = _decimal(snapshot.estimated_monthly_savings)
            if amount is None:
                results.append(self._skip(finding, event, NO_MONETARY_SAVING, observation))
                continue
            if amount == 0:
                results.append(self._skip(finding, event, ZERO_SAVING, observation))
                continue
            if amount < 0:
                results.append(self._skip(finding, event, NEGATIVE_SAVING, observation))
                continue

            currency = str(snapshot.currency or "").strip().upper()
            if not currency:
                results.append(self._skip(finding, event, NO_CURRENCY, observation))
                continue
            if len(currency) != 3 or not currency.isalpha():
                results.append(self._skip(finding, event, INVALID_CURRENCY, observation))
                continue

            provider = normalize_provider(finding.provider)
            expected_currency = {"aws": "USD", "oci": "BRL"}.get(provider)
            if expected_currency is not None and currency != expected_currency:
                logger.warning(
                    "event=opportunity_saving_currency_mismatch finding_id=%s provider=%s "
                    "currency=%s expected_currency=%s",
                    finding.id,
                    provider,
                    currency,
                    expected_currency,
                )

            cloud_account = cloud_accounts.get((provider, finding.account_id))
            if cloud_account is None:
                raise FinOpsLedgerError(
                    "Cloud account for opportunity saving recognition was not found"
                )

            context = {
                "snapshot_source": (
                    "OPPORTUNITY_OBSERVATION" if observation is not None else "FINDING"
                ),
                "opportunity_observation_id": observation.id if observation is not None else None,
                "rule_key": finding.rule_key,
                "resource_id": finding.resource_id,
                "service": finding.service,
                "region": finding.region,
            }
            entry = self.ledger.create_entry(
                entry_type=FinOpsLedgerEntryType.SAVING.value,
                direction=FinOpsLedgerDirection.CREDIT.value,
                cloud_account_id=cloud_account.id,
                amount=amount,
                currency=currency,
                effective_at=event.changed_at,
                source=FinOpsLedgerSource.OPPORTUNITY.value,
                actor=actor,
                description=f'Saving recognized from opportunity "{finding.title}"',
                source_reference=finding.id,
                opportunity_id=finding.id,
                source_event_id=event.id,
                idempotency_key=f"opportunity-treated:{event.id}:saving",
                periodicity=FinOpsLedgerPeriodicity.MONTHLY.value,
                context=context,
            )
            logger.info(
                "event=opportunity_saving_recognized finding_id=%s treatment_event_id=%s "
                "ledger_entry_id=%s amount=%s currency=%s provider=%s observation_id=%s",
                finding.id,
                event.id,
                entry.id,
                entry.amount,
                entry.currency,
                entry.provider,
                observation.id if observation is not None else "none",
            )
            results.append(
                OpportunitySavingRecognitionResult(
                    entry=entry,
                    reason=CREATED,
                    observation_id=observation.id if observation is not None else None,
                )
            )
        return results

    def recognize(
        self,
        finding: Finding,
        event: OpportunityStatusHistory,
        actor: User,
    ) -> OpportunitySavingRecognitionResult:
        return self.recognize_many([(finding, event)], actor)[0]

    def list_recognized_savings(self, opportunity_id: str) -> list[FinOpsLedgerEntry]:
        return list(
            self.db.scalars(
                select(FinOpsLedgerEntry)
                .where(
                    FinOpsLedgerEntry.source == FinOpsLedgerSource.OPPORTUNITY.value,
                    FinOpsLedgerEntry.opportunity_id == opportunity_id,
                    FinOpsLedgerEntry.entry_type == FinOpsLedgerEntryType.SAVING.value,
                )
                .order_by(
                    FinOpsLedgerEntry.effective_at,
                    FinOpsLedgerEntry.created_at,
                    FinOpsLedgerEntry.id,
                )
            )
        )
