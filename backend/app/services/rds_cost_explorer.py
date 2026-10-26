from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from app.services.aws_cost_explorer import (
    AwsBillingUpstreamError,
    AwsCostExplorerClient,
    _map_client_error,
)


@dataclass(frozen=True)
class RdsReservationCoverageObservation:
    total_running_units: Decimal
    reserved_units: Decimal
    coverage_percentage: Decimal
    aws_request_count: int


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class RdsCostExplorerClient(AwsCostExplorerClient):
    """Cost Explorer adapter for RDS Reserved DB Instance observed billing coverage."""

    def get_rds_reservation_coverage(
        self,
        *,
        start_date: str,
        end_date: str,
        linked_account_id: str | None = None,
    ) -> RdsReservationCoverageObservation:
        filters: list[dict[str, Any]] = [
            {
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Relational Database Service"],
                }
            }
        ]
        if linked_account_id:
            filters.append(
                {
                    "Dimensions": {
                        "Key": "LINKED_ACCOUNT",
                        "Values": [linked_account_id],
                    }
                }
            )
        request: dict[str, Any] = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": "DAILY",
            "Metrics": ["Unit"],
            "Filter": filters[0] if len(filters) == 1 else {"And": filters},
        }

        request_count = 0
        next_token: str | None = None
        seen_tokens: set[str] = set()
        total_running = Decimal("0")
        reserved = Decimal("0")

        while True:
            page_request = dict(request)
            if next_token:
                page_request["NextPageToken"] = next_token
            try:
                response = self._client.get_reservation_coverage(**page_request)
            except ClientError as exc:
                raise _map_client_error(exc) from exc
            except BotoCoreError as exc:
                raise AwsBillingUpstreamError(
                    "UPSTREAM_ERROR", "Não foi possível conectar ao AWS Cost Explorer."
                ) from exc
            request_count += 1

            for period in response.get("CoveragesByTime", []):
                total = period.get("Total") or {}
                normalized = total.get("CoverageNormalizedUnits") or {}
                if normalized:
                    total_running += _decimal(normalized.get("TotalRunningNormalizedUnits"))
                    reserved += _decimal(normalized.get("ReservedNormalizedUnits"))
                else:
                    hours = total.get("CoverageHours") or {}
                    total_running += _decimal(hours.get("TotalRunningHours"))
                    reserved += _decimal(hours.get("ReservedHours"))

            token = response.get("NextPageToken")
            if not token:
                break
            token = str(token)
            if token in seen_tokens:
                raise AwsBillingUpstreamError(
                    "PAGINATION_ERROR", "O AWS Cost Explorer repetiu um token de paginação."
                )
            seen_tokens.add(token)
            next_token = token

        percentage = Decimal("0")
        if total_running > 0:
            percentage = min(Decimal("100"), reserved / total_running * Decimal("100"))
        return RdsReservationCoverageObservation(
            total_running_units=total_running,
            reserved_units=reserved,
            coverage_percentage=percentage,
            aws_request_count=request_count,
        )
