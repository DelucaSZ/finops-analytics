"""Database-only query layer for persisted provider-neutral Inventory state."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.inventory import InventoryResource
from app.models.user import User
from app.schemas.inventory import InventorySortDirection, InventorySortField


@dataclass(frozen=True, slots=True)
class InventoryQuery:
    provider: str | None = None
    account_id: int | None = None
    region: str | None = None
    resource_type: str | None = None
    lifecycle_status: str | None = None
    presence_status: str | None = None
    service: str | None = None
    search: str | None = None
    sort: InventorySortField = InventorySortField.LAST_SEEN_AT
    direction: InventorySortDirection = InventorySortDirection.DESC
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True, slots=True)
class InventoryResourceView:
    resource: InventoryResource
    account_name: str | None


@dataclass(frozen=True, slots=True)
class InventoryPage:
    items: tuple[InventoryResourceView, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class InventoryAccountView:
    id: int
    name: str
    native_account_id: str
    provider: str


@dataclass(frozen=True, slots=True)
class InventoryOptions:
    providers: tuple[str, ...]
    accounts: tuple[InventoryAccountView, ...]
    regions: tuple[str, ...]
    resource_types: tuple[str, ...]
    services: tuple[str, ...]
    lifecycle_statuses: tuple[str, ...]
    presence_statuses: tuple[str, ...]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class InventoryQueryService:
    """Compose authorized Inventory SQL without invoking provider/discovery services.

    The current authorization model grants every authenticated user read access to
    CloudAccount records. Keeping that policy behind one account-scope subquery
    gives Inventory a single enforcement point and allows a future account ACL to
    be introduced without changing endpoint/query semantics.
    """

    SORT_COLUMNS = {
        InventorySortField.NAME: InventoryResource.name,
        InventorySortField.PROVIDER: InventoryResource.provider,
        InventorySortField.ACCOUNT: CloudAccount.name,
        InventorySortField.RESOURCE_TYPE: InventoryResource.resource_type,
        InventorySortField.SERVICE: InventoryResource.service,
        InventorySortField.REGION: InventoryResource.region,
        InventorySortField.LIFECYCLE_STATUS: InventoryResource.lifecycle_status,
        InventorySortField.PRESENCE_STATUS: InventoryResource.presence_status,
        InventorySortField.FIRST_SEEN_AT: InventoryResource.first_seen_at,
        InventorySortField.LAST_SEEN_AT: InventoryResource.last_seen_at,
    }

    @staticmethod
    def _authorized_account_ids(user: User) -> Select:
        if user is None:  # defensive: routes already require authenticated users
            raise ValueError("Inventory account scope requires an authenticated user")
        return select(CloudAccount.id)

    def _predicates(self, user: User, query: InventoryQuery):
        predicates = [InventoryResource.cloud_account_id.in_(self._authorized_account_ids(user))]
        if query.provider is not None:
            predicates.append(InventoryResource.provider == query.provider)
        if query.account_id is not None:
            predicates.append(InventoryResource.cloud_account_id == query.account_id)
        if query.region is not None:
            predicates.append(InventoryResource.region == query.region)
        if query.resource_type is not None:
            predicates.append(InventoryResource.resource_type == query.resource_type)
        if query.lifecycle_status is not None:
            predicates.append(InventoryResource.lifecycle_status == query.lifecycle_status)
        if query.presence_status is not None:
            predicates.append(InventoryResource.presence_status == query.presence_status)
        if query.service is not None:
            predicates.append(InventoryResource.service == query.service)

        search = (query.search or "").strip()
        if search:
            pattern = f"%{_escape_like(search)}%"
            predicates.append(
                or_(
                    InventoryResource.name.ilike(pattern, escape="\\"),
                    InventoryResource.resource_id.ilike(pattern, escape="\\"),
                    InventoryResource.native_account_id.ilike(pattern, escape="\\"),
                    InventoryResource.resource_type.ilike(pattern, escape="\\"),
                    InventoryResource.service.ilike(pattern, escape="\\"),
                    InventoryResource.region.ilike(pattern, escape="\\"),
                )
            )
        return predicates

    def list_resources(self, db: Session, *, user: User, query: InventoryQuery) -> InventoryPage:
        predicates = self._predicates(user, query)
        total = int(
            db.scalar(select(func.count()).select_from(InventoryResource).where(*predicates)) or 0
        )

        sort_column = self.SORT_COLUMNS[query.sort]
        order = asc if query.direction == InventorySortDirection.ASC else desc
        statement = (
            select(InventoryResource, CloudAccount.name.label("account_name"))
            .join(CloudAccount, CloudAccount.id == InventoryResource.cloud_account_id)
            .where(*predicates)
            .order_by(order(sort_column), order(InventoryResource.id))
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        rows = db.execute(statement).all()
        items = tuple(InventoryResourceView(resource=row[0], account_name=row[1]) for row in rows)
        total_pages = (total + query.page_size - 1) // query.page_size if total else 0
        return InventoryPage(
            items=items,
            page=query.page,
            page_size=query.page_size,
            total=total,
            total_pages=total_pages,
        )

    def get_resource(
        self, db: Session, *, user: User, resource_id: int
    ) -> InventoryResourceView | None:
        statement = (
            select(InventoryResource, CloudAccount.name.label("account_name"))
            .join(CloudAccount, CloudAccount.id == InventoryResource.cloud_account_id)
            .where(
                InventoryResource.id == resource_id,
                InventoryResource.cloud_account_id.in_(self._authorized_account_ids(user)),
            )
        )
        row = db.execute(statement).one_or_none()
        if row is None:
            return None
        return InventoryResourceView(resource=row[0], account_name=row[1])

    def options(
        self,
        db: Session,
        *,
        user: User,
        provider: str | None = None,
        account_id: int | None = None,
    ) -> InventoryOptions:
        criteria = InventoryQuery(provider=provider, account_id=account_id)
        predicates = self._predicates(user, criteria)

        def distinct_values(column) -> tuple[str, ...]:
            rows = db.scalars(
                select(column)
                .select_from(InventoryResource)
                .where(*predicates, column.is_not(None), column != "")
                .distinct()
                .order_by(column)
            ).all()
            return tuple(str(value) for value in rows)

        account_rows = db.execute(
            select(
                CloudAccount.id,
                CloudAccount.name,
                CloudAccount.native_account_id,
                CloudAccount.provider,
            )
            .join(InventoryResource, InventoryResource.cloud_account_id == CloudAccount.id)
            .where(*predicates)
            .distinct()
            .order_by(CloudAccount.name, CloudAccount.id)
        ).all()

        return InventoryOptions(
            providers=distinct_values(InventoryResource.provider),
            accounts=tuple(
                InventoryAccountView(
                    id=row[0], name=row[1], native_account_id=row[2], provider=row[3]
                )
                for row in account_rows
            ),
            regions=distinct_values(InventoryResource.region),
            resource_types=distinct_values(InventoryResource.resource_type),
            services=distinct_values(InventoryResource.service),
            lifecycle_statuses=distinct_values(InventoryResource.lifecycle_status),
            presence_statuses=distinct_values(InventoryResource.presence_status),
        )
