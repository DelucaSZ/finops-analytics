from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.services.collection_errors import GENERIC_ERROR, sanitize_collection_error


ERROR_SUMMARY_MAX_LENGTH = 240
TERMINAL_COLLECTION_STATUSES = (
    CollectionRunStatus.SUCCESS,
    CollectionRunStatus.FAILED,
)


def _scope(statement, *, provider: str | None, account_id: str | None):
    if provider:
        statement = statement.where(CollectionRun.provider == provider.lower())
    if account_id:
        statement = statement.where(CollectionRun.account_id == account_id)
    return statement


def _ranked_runs(
    *,
    provider: str | None,
    account_id: str | None,
    terminal_only: bool,
    name: str,
):
    statement = select(
        CollectionRun.id.label("run_id"),
        CollectionRun.provider.label("provider"),
        CollectionRun.account_id.label("account_id"),
        CollectionRun.started_at.label("started_at"),
        CollectionRun.finished_at.label("finished_at"),
        CollectionRun.status.label("status"),
        CollectionRun.error_detail.label("error_detail"),
        func.row_number()
        .over(
            partition_by=(CollectionRun.provider, CollectionRun.account_id),
            # Match the collection/dashboard convention: the most recently started
            # execution wins, with the immutable run id as deterministic tiebreaker.
            order_by=(CollectionRun.started_at.desc(), CollectionRun.id.desc()),
        )
        .label("run_rank"),
    )
    statement = _scope(statement, provider=provider, account_id=account_id)
    if terminal_only:
        statement = statement.where(CollectionRun.status.in_(TERMINAL_COLLECTION_STATUSES))
    return statement.cte(name)


def _latest(ranked, *, name: str):
    return select(ranked).where(ranked.c.run_rank == 1).cte(name)


def _error_summary(value: object | None) -> str:
    summary = sanitize_collection_error(value) or GENERIC_ERROR
    return summary[:ERROR_SUMMARY_MAX_LENGTH]


def collection_failure_insights(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
    max_items: int = 10,
) -> dict:
    """Return only currently actionable collection failures for the dashboard.

    A failure is current when the latest *terminal* run for an enabled account is
    FAILED. A newer RUNNING execution does not resolve it; a newer SUCCESS does.
    Historical failures remain available from Collections but are not surfaced here.
    """

    latest_run = _latest(
        _ranked_runs(
            provider=provider,
            account_id=account_id,
            terminal_only=False,
            name="dashboard_insight_all_ranked",
        ),
        name="dashboard_insight_latest_run",
    )
    latest_terminal = _latest(
        _ranked_runs(
            provider=provider,
            account_id=account_id,
            terminal_only=True,
            name="dashboard_insight_terminal_ranked",
        ),
        name="dashboard_insight_latest_terminal",
    )

    identity_join = and_(
        latest_terminal.c.provider == latest_run.c.provider,
        latest_terminal.c.account_id == latest_run.c.account_id,
    )
    account_join = and_(
        latest_terminal.c.provider == CloudAccount.provider,
        latest_terminal.c.account_id == CloudAccount.native_account_id,
    )

    rows = db.execute(
        select(
            latest_terminal.c.provider,
            latest_terminal.c.account_id,
            CloudAccount.name.label("account_name"),
            latest_terminal.c.run_id.label("failed_run_id"),
            latest_terminal.c.started_at.label("failed_started_at"),
            latest_terminal.c.finished_at.label("failed_finished_at"),
            latest_terminal.c.status.label("failed_status"),
            latest_terminal.c.error_detail.label("failed_error_detail"),
            latest_run.c.run_id.label("latest_run_id"),
            latest_run.c.started_at.label("latest_run_started_at"),
            latest_run.c.status.label("latest_run_status"),
            func.count().over().label("failure_count"),
        )
        .select_from(latest_terminal)
        .join(latest_run, identity_join)
        # Only accounts still in the operational scope should keep a dashboard
        # alert alive. Deleted accounts have no row; disabled accounts are hidden.
        .join(CloudAccount, account_join)
        .where(
            latest_terminal.c.status == CollectionRunStatus.FAILED,
            CloudAccount.enabled.is_(True),
        )
        .order_by(
            latest_terminal.c.started_at.desc(),
            latest_terminal.c.provider,
            latest_terminal.c.account_id,
        )
        .limit(max_items)
    ).all()

    count = int(rows[0].failure_count) if rows else 0
    items: list[dict] = []
    for row in rows:
        newer_run = None
        if row.latest_run_id != row.failed_run_id:
            newer_run = {
                "id": row.latest_run_id,
                "status": row.latest_run_status,
                "started_at": row.latest_run_started_at,
            }
        items.append(
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.account_name,
                "collection_run_id": row.failed_run_id,
                "started_at": row.failed_started_at,
                "finished_at": row.failed_finished_at,
                "status": row.failed_status,
                "error_summary": _error_summary(row.failed_error_detail),
                "newer_run": newer_run,
            }
        )

    return {
        "collection_failures": {
            "count": count,
            "items": items,
            "truncated": count > len(items),
        }
    }
