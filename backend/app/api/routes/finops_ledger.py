from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_operator, require_user
from app.db.session import get_db
from app.models.finops_ledger import FinOpsLedgerEntry
from app.models.user import User
from app.schemas.finops_ledger import (
    FinOpsLedgerBalance,
    FinOpsLedgerEntryRead,
    FinOpsLedgerManualCreate,
    FinOpsLedgerPage,
    FinOpsLedgerReverse,
)
from app.services.finops_ledger import (
    FinOpsLedgerConflictError,
    FinOpsLedgerError,
    FinOpsLedgerFilters,
    FinOpsLedgerNotFoundError,
    FinOpsLedgerService,
)

router = APIRouter(
    prefix="/finops/ledger",
    tags=["finops-ledger"],
    dependencies=[Depends(require_user)],
)


def _filters(
    *,
    provider: str | None,
    account_id: str | None,
    currency: str | None,
    entry_type: str | None,
    direction: str | None,
    source: str | None,
    effective_from: datetime | None,
    effective_to: datetime | None,
) -> FinOpsLedgerFilters:
    if effective_from and effective_to:
        left = (
            effective_from
            if effective_from.tzinfo
            else effective_from.replace(tzinfo=effective_to.tzinfo)
        )
        right = (
            effective_to
            if effective_to.tzinfo
            else effective_to.replace(tzinfo=effective_from.tzinfo)
        )
        if left >= right:
            raise HTTPException(status_code=422, detail="effective_from must precede effective_to")
    return FinOpsLedgerFilters(
        provider=provider,
        account_id=account_id,
        currency=currency,
        entry_type=entry_type,
        direction=direction,
        source=source,
        effective_from=effective_from,
        effective_to=effective_to,
    )


def _validation_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _entry_read(
    entry: FinOpsLedgerEntry,
    reversed_by_id: str | None = None,
) -> FinOpsLedgerEntryRead:
    return FinOpsLedgerEntryRead.model_validate(entry).model_copy(
        update={
            "is_reversed": reversed_by_id is not None,
            "reversed_by_id": reversed_by_id,
        }
    )


@router.get("", response_model=FinOpsLedgerPage)
def list_finops_ledger(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    entry_type: str | None = Query(default=None, max_length=24),
    direction: str | None = Query(default=None, max_length=8),
    source: str | None = Query(default=None, max_length=24),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    try:
        service = FinOpsLedgerService(db)
        result = service.list_entries(
            _filters(
                provider=provider,
                account_id=account_id,
                currency=currency,
                entry_type=entry_type,
                direction=direction,
                source=source,
                effective_from=effective_from,
                effective_to=effective_to,
            ),
            page=page,
            page_size=page_size,
        )
        reversals = service.reversal_map([entry.id for entry in result["items"]])
        return {
            **result,
            "items": [_entry_read(entry, reversals.get(entry.id)) for entry in result["items"]],
        }
    except FinOpsLedgerError as exc:
        raise _validation_error(exc) from exc
    except ValueError as exc:
        raise _validation_error(exc) from exc


@router.get("/summary", response_model=dict[str, FinOpsLedgerBalance])
def finops_ledger_summary(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    entry_type: str | None = Query(default=None, max_length=24),
    direction: str | None = Query(default=None, max_length=8),
    source: str | None = Query(default=None, max_length=24),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return FinOpsLedgerService(db).calculate_balances(
            _filters(
                provider=provider,
                account_id=account_id,
                currency=currency,
                entry_type=entry_type,
                direction=direction,
                source=source,
                effective_from=effective_from,
                effective_to=effective_to,
            )
        )
    except FinOpsLedgerError as exc:
        raise _validation_error(exc) from exc
    except ValueError as exc:
        raise _validation_error(exc) from exc


@router.post(
    "/manual",
    response_model=FinOpsLedgerEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_finops_ledger_entry(
    payload: FinOpsLedgerManualCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> FinOpsLedgerEntryRead:
    service = FinOpsLedgerService(db)
    try:
        entry = service.create_manual_entry(
            entry_type=payload.entry_type,
            direction=payload.direction,
            provider=payload.provider,
            cloud_account_id=payload.cloud_account_id,
            amount=payload.amount,
            currency=payload.currency,
            effective_at=datetime.combine(payload.effective_date, time.min, tzinfo=UTC),
            actor=actor,
            description=payload.description,
            manual_entry_request_id=str(payload.manual_entry_request_id),
            periodicity=payload.periodicity,
            reference_period_start=payload.reference_period_start,
            reference_period_end=payload.reference_period_end,
        )
        db.commit()
        db.refresh(entry)
        return _entry_read(entry)
    except FinOpsLedgerError as exc:
        db.rollback()
        raise _validation_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise _validation_error(exc) from exc


@router.post("/{entry_id}/reverse", response_model=FinOpsLedgerEntryRead)
def reverse_finops_ledger_entry(
    entry_id: str,
    payload: FinOpsLedgerReverse,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> FinOpsLedgerEntryRead:
    service = FinOpsLedgerService(db)
    try:
        reversal = service.reverse_entry(entry_id, actor=actor, description=payload.reason)
        db.commit()
        db.refresh(reversal)
        return _entry_read(reversal)
    except FinOpsLedgerNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FinOpsLedgerConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FinOpsLedgerError as exc:
        db.rollback()
        raise _validation_error(exc) from exc


@router.get("/{entry_id}", response_model=FinOpsLedgerEntryRead)
def get_finops_ledger_entry(
    entry_id: str,
    db: Session = Depends(get_db),
) -> FinOpsLedgerEntryRead:
    try:
        service = FinOpsLedgerService(db)
        entry = service.get_entry(entry_id)
        reversal = service.reversal_map([entry.id]).get(entry.id)
        return _entry_read(entry, reversal)
    except FinOpsLedgerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
