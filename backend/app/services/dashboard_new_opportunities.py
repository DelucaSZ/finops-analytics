from __future__ import annotations

import base64
import hashlib
import hmac
import json
import zlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import ceil
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import AwsAccount, CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding
from app.services.opportunity_query import (
    OpportunityFilters,
    _account_join,
    _apply_filters,
    _order_expression,
    serialize_list_item,
)
from app.services.opportunity_run_comparison import (
    OpportunityRunContext,
    _classification_condition,
    resolve_run_context,
)

DashboardComparisonKind = Literal["new_vs_previous", "first_seen", "reappeared"]
_CONTEXT_VERSION = "v1"
_MAX_CONTEXT_LENGTH = 12_000
_MAX_PAIRS = 200


class DashboardComparisonContextError(ValueError):
    def __init__(self, message: str, *, code: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class DashboardComparisonPair:
    provider: str
    account_id: str
    target: CollectionRun
    baseline: CollectionRun
    context: OpportunityRunContext


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _context_signature(payload: bytes) -> bytes:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        b"dashboard-new-opportunities\x00" + payload,
        hashlib.sha256,
    ).digest()


def _encode_context(
    *,
    pairs: list[DashboardComparisonPair],
    provider: str | None,
    account_id: str | None,
) -> str:
    document = {
        "v": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": {"provider": provider, "account_id": account_id},
        "pairs": [
            {
                "p": pair.provider,
                "a": pair.account_id,
                "t": pair.target.id,
                "b": pair.baseline.id,
            }
            for pair in pairs
        ],
    }
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    token = (
        f"{_CONTEXT_VERSION}.{_b64encode(compressed)}."
        f"{_b64encode(_context_signature(compressed))}"
    )
    if len(token) > _MAX_CONTEXT_LENGTH:
        raise DashboardComparisonContextError(
            "O contexto consolidado excede o limite seguro para um deep link.",
            code="COMPARISON_CONTEXT_TOO_LARGE",
            status_code=422,
        )
    return token


def _decode_document(token: str) -> dict:
    if not token or len(token) > _MAX_CONTEXT_LENGTH:
        raise DashboardComparisonContextError(
            "Contexto de comparação inválido.",
            code="INVALID_COMPARISON_CONTEXT",
        )
    try:
        version, encoded_payload, encoded_signature = token.split(".", 2)
        payload = _b64decode(encoded_payload)
        signature = _b64decode(encoded_signature)
    except (ValueError, TypeError):
        raise DashboardComparisonContextError(
            "Contexto de comparação inválido.",
            code="INVALID_COMPARISON_CONTEXT",
        ) from None
    signature_valid = hmac.compare_digest(signature, _context_signature(payload))
    if version != _CONTEXT_VERSION or not signature_valid:
        raise DashboardComparisonContextError(
            "Contexto de comparação inválido ou adulterado.",
            code="INVALID_COMPARISON_CONTEXT",
        )
    try:
        document = json.loads(zlib.decompress(payload))
    except (ValueError, TypeError, zlib.error, json.JSONDecodeError):
        raise DashboardComparisonContextError(
            "Contexto de comparação inválido.",
            code="INVALID_COMPARISON_CONTEXT",
        ) from None
    pairs = document.get("pairs")
    if document.get("v") != 1 or not isinstance(pairs, list) or len(pairs) > _MAX_PAIRS:
        raise DashboardComparisonContextError(
            "Contexto de comparação incompatível.",
            code="INVALID_COMPARISON_CONTEXT",
        )
    return document


def _latest_success_targets(
    db: Session,
    *,
    provider: str | None,
    account_id: str | None,
) -> list[CollectionRun]:
    ranked = select(
        CollectionRun.id.label("run_id"),
        func.row_number()
        .over(
            partition_by=(CollectionRun.provider, CollectionRun.account_id),
            order_by=(CollectionRun.started_at.desc(), CollectionRun.id.desc()),
        )
        .label("run_rank"),
    ).where(CollectionRun.status == CollectionRunStatus.SUCCESS)
    if provider:
        ranked = ranked.where(CollectionRun.provider == provider.lower())
    if account_id:
        ranked = ranked.where(CollectionRun.account_id == account_id)
    ranked_cte = ranked.cte("dashboard_new_success_ranked")
    return list(
        db.scalars(
            select(CollectionRun)
            .join(ranked_cte, CollectionRun.id == ranked_cte.c.run_id)
            .where(ranked_cte.c.run_rank == 1)
            .order_by(CollectionRun.provider, CollectionRun.account_id)
        )
    )


def _latest_pairs(
    db: Session,
    *,
    provider: str | None,
    account_id: str | None,
) -> tuple[list[DashboardComparisonPair], list[OpportunityRunContext]]:
    contexts = [
        resolve_run_context(db, target)
        for target in _latest_success_targets(db, provider=provider, account_id=account_id)
    ]
    pairs = [
        DashboardComparisonPair(
            provider=context.target.provider,
            account_id=context.target.account_id,
            target=context.target,
            baseline=context.baseline,
            context=context,
        )
        for context in contexts
        if context.comparable and context.baseline is not None
    ]
    return pairs, contexts


def _load_context_pairs(
    db: Session,
    token: str,
) -> tuple[list[DashboardComparisonPair], dict]:
    document = _decode_document(token)
    raw_pairs = document["pairs"]
    run_ids = {
        run_id
        for pair in raw_pairs
        for run_id in (pair.get("t"), pair.get("b"))
        if isinstance(run_id, str) and run_id
    }
    runs = {
        run.id: run
        for run in db.scalars(select(CollectionRun).where(CollectionRun.id.in_(run_ids)))
    }
    pairs: list[DashboardComparisonPair] = []
    for raw_pair in raw_pairs:
        provider = str(raw_pair.get("p") or "").lower()
        account_id = str(raw_pair.get("a") or "")
        target = runs.get(raw_pair.get("t"))
        baseline = runs.get(raw_pair.get("b"))
        if target is None or baseline is None:
            raise DashboardComparisonContextError(
                "Os detalhes desta comparação não estão mais disponíveis.",
                code="COMPARISON_CONTEXT_EXPIRED",
                status_code=410,
            )
        if (
            target.status != CollectionRunStatus.SUCCESS
            or baseline.status != CollectionRunStatus.SUCCESS
            or target.provider.lower() != provider
            or baseline.provider.lower() != provider
            or target.account_id != account_id
            or baseline.account_id != account_id
            or baseline.started_at >= target.started_at
        ):
            raise DashboardComparisonContextError(
                "Contexto de comparação inconsistente.",
                code="INVALID_COMPARISON_CONTEXT",
            )
        observations_unavailable = (
            not target.detailed_observations_available
            or not baseline.detailed_observations_available
        )
        if observations_unavailable:
            raise DashboardComparisonContextError(
                "Os detalhes desta comparação não estão mais disponíveis devido à "
                "política de retenção.",
                code="COMPARISON_CONTEXT_EXPIRED",
                status_code=410,
            )
        current_context = resolve_run_context(db, target)
        frozen_context = replace(
            current_context,
            baseline=baseline,
            comparable=True,
            reason=None,
        )
        pairs.append(
            DashboardComparisonPair(
                provider=provider,
                account_id=account_id,
                target=target,
                baseline=baseline,
                context=frozen_context,
            )
        )
    return pairs, document


def _covered_by_run(run_id: str):
    return (
        select(CollectionScopeExecution.id)
        .where(
            CollectionScopeExecution.collection_run_id == run_id,
            CollectionScopeExecution.provider == Finding.provider,
            CollectionScopeExecution.account_id == Finding.account_id,
            CollectionScopeExecution.rule_key == Finding.rule_key,
            CollectionScopeExecution.status == CollectionScopeExecutionStatus.SUCCESS,
            or_(Finding.region.is_(None), CollectionScopeExecution.region == Finding.region),
        )
        .correlate(Finding)
        .exists()
    )


def _has_scope_snapshots(db: Session, run_id: str) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(CollectionScopeExecution)
            .where(CollectionScopeExecution.collection_run_id == run_id)
        )
    )


def _pair_new_condition(db: Session, pair: DashboardComparisonPair):
    condition = _classification_condition(pair.context, "new_vs_previous")
    if _has_scope_snapshots(db, pair.baseline.id):
        condition = and_(condition, _covered_by_run(pair.baseline.id))
    return condition


def _pair_condition(
    db: Session,
    pair: DashboardComparisonPair,
    kind: DashboardComparisonKind,
):
    new_condition = _pair_new_condition(db, pair)
    if kind == "new_vs_previous":
        condition = new_condition
    elif kind == "first_seen":
        condition = and_(
            new_condition,
            _classification_condition(pair.context, "first_seen"),
        )
    elif kind == "reappeared":
        condition = and_(
            new_condition,
            _classification_condition(pair.context, "reappeared"),
        )
    else:
        raise DashboardComparisonContextError(
            "Tipo de comparação não suportado.",
            code="INVALID_COMPARISON_KIND",
        )
    return and_(
        Finding.provider == pair.provider,
        Finding.account_id == pair.account_id,
        condition,
    )


def _comparison_condition(
    db: Session,
    pairs: list[DashboardComparisonPair],
    kind: DashboardComparisonKind,
):
    conditions = [_pair_condition(db, pair, kind) for pair in pairs]
    if not conditions:
        return Finding.id.is_(None)
    return or_(*conditions)


def _operational_condition(condition):
    # The target observation already freezes the `current` membership at Dashboard time.
    # Lifecycle/archive suppression deliberately follows the central operational backlog rules.
    return and_(
        condition,
        Finding.archived_at.is_(None),
        Finding.status != "rejected",
    )


def dashboard_new_since_previous(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> dict:
    provider = provider.lower() if provider else None
    pairs, contexts = _latest_pairs(db, provider=provider, account_id=account_id)
    base = _operational_condition(_comparison_condition(db, pairs, "new_vs_previous"))
    first_seen = _operational_condition(_comparison_condition(db, pairs, "first_seen"))
    reappeared = _operational_condition(_comparison_condition(db, pairs, "reappeared"))
    count = int(db.scalar(select(func.count(func.distinct(Finding.id))).where(base)) or 0)
    first_seen_count = int(
        db.scalar(select(func.count(func.distinct(Finding.id))).where(first_seen)) or 0
    )
    reappeared_count = int(
        db.scalar(select(func.count(func.distinct(Finding.id))).where(reappeared)) or 0
    )
    without_baseline = sum(context.reason == "NO_BASELINE" for context in contexts)
    unavailable = sum(
        not context.comparable and context.reason not in {"NO_BASELINE"}
        for context in contexts
    )
    token = _encode_context(
        pairs=pairs,
        provider=provider,
        account_id=account_id,
    )
    generated_at = _decode_document(token)["generated_at"]
    return {
        "count": count,
        "first_seen_count": first_seen_count,
        "reappeared_count": reappeared_count,
        "comparable_accounts": len(pairs),
        "accounts_without_baseline": int(without_baseline),
        "unavailable_accounts": int(unavailable),
        "rules_version_changed": any(
            context.rules_version_changed is True for context in contexts if context.comparable
        ),
        "partial_coverage_accounts": sum(
            context.partial_coverage for context in contexts if context.comparable
        ),
        "comparison_context": token,
        "generated_at": generated_at,
    }


def _filtered_statement(statement, filters: OpportunityFilters):
    # The frozen comparison defines current membership and always remains active/non-rejected.
    safe_filters = replace(
        filters,
        collection_run_id=None,
        first_seen_collection_run_id=None,
        discovery_type=None,
        baseline_collection_run_id=None,
        comparison_available=True,
        current=False,
        archive_state="all",
    )
    return _apply_filters(statement, safe_filters)


def list_dashboard_new_opportunities(
    db: Session,
    *,
    comparison_context: str,
    comparison_kind: DashboardComparisonKind,
    filters: OpportunityFilters,
    page: int,
    page_size: int,
    sort: str,
    order: str,
) -> dict:
    pairs, _ = _load_context_pairs(db, comparison_context)
    membership = _operational_condition(_comparison_condition(db, pairs, comparison_kind))
    base = (
        select(Finding, CloudAccount, AwsAccount)
        .outerjoin(CloudAccount, _account_join())
        .outerjoin(AwsAccount, AwsAccount.cloud_account_id == CloudAccount.id)
        .where(membership)
    )
    base = _filtered_statement(base, filters)
    count_query = select(func.count(func.distinct(Finding.id))).where(membership)
    count_query = _filtered_statement(count_query, filters)
    total = int(db.scalar(count_query) or 0)
    order_expression = _order_expression(sort)
    ordering = order_expression.desc() if order == "desc" else order_expression.asc()
    rows = db.execute(
        base.order_by(ordering, Finding.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [
            serialize_list_item(finding, account, aws_configuration)
            for finding, account, aws_configuration in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


def dashboard_new_opportunity_stats(
    db: Session,
    *,
    comparison_context: str,
    comparison_kind: DashboardComparisonKind,
    filters: OpportunityFilters,
) -> dict[str, int]:
    pairs, _ = _load_context_pairs(db, comparison_context)
    membership = _operational_condition(_comparison_condition(db, pairs, comparison_kind))
    statement = (
        select(Finding.status, func.count(func.distinct(Finding.id)))
        .where(membership)
        .group_by(Finding.status)
    )
    safe_filters = replace(filters, status=None)
    statement = _filtered_statement(statement, safe_filters)
    counts = {status: int(count) for status, count in db.execute(statement).all()}
    return {
        "open": counts.get("open", 0),
        "treated": counts.get("treated", 0),
        "rejected": 0,
    }


def context_scope(comparison_context: str) -> dict:
    return _decode_document(comparison_context).get("scope") or {}
