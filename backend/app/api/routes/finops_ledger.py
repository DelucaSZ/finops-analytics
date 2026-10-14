from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.schemas.finops_ledger import (
    FinOpsLedgerBalance,
    FinOpsLedgerEntryRead,
    FinOpsLedgerPage,
)
from app.services.finops_ledger import (
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
        return FinOpsLedgerService(db).list_entries(
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


@router.get("/{entry_id}", response_model=FinOpsLedgerEntryRead)
def get_finops_ledger_entry(
    entry_id: str,
    db: Session = Depends(get_db),
):
    try:
        return FinOpsLedgerService(db).get_entry(entry_id)
    except FinOpsLedgerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
