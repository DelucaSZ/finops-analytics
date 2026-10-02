from __future__ import annotations

import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_clients import OciPageFailure, classify_oci_failure, list_all_pages
from app.services.oci_discovery_models import OciDiscoveryIssue

logger = logging.getLogger(__name__)


class OciFatalDiscoveryAbort(RuntimeError):
    def __init__(self, issue: OciDiscoveryIssue):
        super().__init__(issue.message)
        self.issue = issue


class OciDiscoveryOperations:
    """Shared paginated OCI call runner with safe failure classification and logging."""

    def __init__(
        self,
        snapshot: OciConnectionSnapshot,
        errors: list[OciDiscoveryIssue],
    ) -> None:
        self.snapshot = snapshot
        self.errors = errors

    def paged(
        self,
        *,
        source: str,
        operation: str,
        region: str | None,
        compartment_id: str | None,
        call: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        resource_type: str | None = None,
        item_extractor: Callable[[Any], list[Any]] | None = None,
    ) -> tuple[list[Any], bool]:
        started = perf_counter()
        try:
            page_result = list_all_pages(
                call,
                *args,
                item_extractor=item_extractor,
                **(kwargs or {}),
            )
        except OciPageFailure as exc:
            self._handle_failure(
                exc.cause,
                source=source,
                operation=operation,
                region=region,
                compartment_id=compartment_id,
                resource_type=resource_type,
            )
            self._log_operation(
                source=source,
                operation=operation,
                region=region,
                compartment_id=compartment_id,
                count=len(exc.items),
                pages=exc.pages,
                started=started,
                partial=True,
            )
            return exc.items, False

        self._log_operation(
            source=source,
            operation=operation,
            region=region,
            compartment_id=compartment_id,
            count=len(page_result.items),
            pages=page_result.pages,
            started=started,
        )
        return page_result.items, True

    def _handle_failure(
        self,
        exc: Exception,
        *,
        source: str,
        operation: str,
        region: str | None,
        compartment_id: str | None,
        resource_type: str | None,
    ) -> None:
        classification = classify_oci_failure(exc)
        issue = OciDiscoveryIssue(
            category=classification.category,
            source=source,
            operation=operation,
            message=classification.message,
            region=region,
            compartment_id=compartment_id,
            resource_type=resource_type,
            fatal=classification.authentication_fatal,
        )
        if classification.authentication_fatal:
            raise OciFatalDiscoveryAbort(issue) from None
        self.errors.append(issue)

    def _log_operation(
        self,
        *,
        source: str,
        operation: str,
        region: str | None,
        compartment_id: str | None,
        count: int,
        pages: int,
        started: float,
        partial: bool = False,
    ) -> None:
        logger.info(
            "OCI discovery cloud_account_id=%s provider=oci region=%s compartment_id=%s "
            "source=%s operation=%s resources_found=%s pages=%s duration_ms=%s partial=%s",
            self.snapshot.cloud_account_id,
            region,
            compartment_id,
            source,
            operation,
            count,
            pages,
            round((perf_counter() - started) * 1000),
            partial,
        )
