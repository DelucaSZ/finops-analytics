from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.schemas.billing import BillingGranularity, BillingGroupBy, BillingMetric
from app.services.aws_auth import BOTO_CONFIG

COST_EXPLORER_REGION = "us-east-1"

AWS_METRICS = {
    BillingMetric.AMORTIZED_COST: "AmortizedCost",
    BillingMetric.NET_AMORTIZED_COST: "NetAmortizedCost",
    BillingMetric.UNBLENDED_COST: "UnblendedCost",
}
AWS_GROUPS = {
    BillingGroupBy.SERVICE: "SERVICE",
    BillingGroupBy.ACCOUNT: "LINKED_ACCOUNT",
}


class AwsBillingUpstreamError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class CostExplorerPages:
    pages: tuple[dict[str, Any], ...]
    aws_request_count: int


def build_cost_and_usage_query(
    *,
    start_date: str,
    end_date: str,
    granularity: BillingGranularity,
    metric: BillingMetric,
    group_by: BillingGroupBy,
    exclude_record_types: tuple[str, ...],
    linked_account_id: str | None = None,
) -> dict[str, Any]:
    """Translate the provider-neutral DeepOps billing request to Cost Explorer."""

    query: dict[str, Any] = {
        "TimePeriod": {"Start": start_date, "End": end_date},
        "Granularity": granularity.value,
        "Metrics": [AWS_METRICS[metric]],
    }

    filters: list[dict[str, Any]] = []
    if linked_account_id:
        filters.append(
            {
                "Dimensions": {
                    "Key": "LINKED_ACCOUNT",
                    "Values": [linked_account_id],
                }
            }
        )
    if exclude_record_types:
        filters.append(
            {
                "Not": {
                    "Dimensions": {
                        "Key": "RECORD_TYPE",
                        "Values": list(exclude_record_types),
                    }
                }
            }
        )
    if len(filters) == 1:
        query["Filter"] = filters[0]
    elif filters:
        query["Filter"] = {"And": filters}

    aws_group = AWS_GROUPS.get(group_by)
    if aws_group:
        query["GroupBy"] = [{"Type": "DIMENSION", "Key": aws_group}]
    return query


def _map_client_error(exc: ClientError) -> AwsBillingUpstreamError:
    error = exc.response.get("Error", {})
    aws_code = str(error.get("Code") or "")
    if aws_code in {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedException",
        "UnauthorizedOperation",
    }:
        return AwsBillingUpstreamError(
            "ACCESS_DENIED",
            "Não foi possível consultar Billing para esta conta com as credenciais configuradas.",
        )
    if aws_code in {"DataUnavailableException"}:
        return AwsBillingUpstreamError(
            "COST_EXPLORER_UNAVAILABLE",
            "Os dados do AWS Cost Explorer estão indisponíveis para esta conta no momento.",
        )
    if aws_code in {
        "LimitExceededException",
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
    }:
        return AwsBillingUpstreamError(
            "THROTTLED",
            "O AWS Cost Explorer limitou temporariamente as consultas. Tente novamente.",
        )
    if aws_code in {"InvalidNextTokenException", "RequestChangedException"}:
        return AwsBillingUpstreamError(
            "PAGINATION_ERROR",
            "O AWS Cost Explorer não conseguiu concluir a paginação da consulta.",
        )
    if aws_code in {"BillingViewHealthStatusException", "ResourceNotFoundException"}:
        return AwsBillingUpstreamError(
            "INVALID_BILLING_SCOPE",
            "O escopo de Billing solicitado não está disponível para esta credencial.",
        )
    if aws_code in {"BillExpirationException", "ValidationException"}:
        return AwsBillingUpstreamError(
            "INVALID_REQUEST",
            "O AWS Cost Explorer rejeitou o período ou os filtros da consulta.",
        )
    return AwsBillingUpstreamError(
        "UPSTREAM_ERROR",
        "Não foi possível concluir a consulta no AWS Cost Explorer.",
    )


class AwsCostExplorerClient:
    def __init__(
        self,
        session: boto3.Session | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        elif session is not None:
            # Cost Explorer is a global billing endpoint exposed from us-east-1.
            self._client = session.client(
                "ce",
                region_name=COST_EXPLORER_REGION,
                config=BOTO_CONFIG,
            )
        else:
            raise ValueError("session or client is required")

    def get_cost_and_usage(self, query: dict[str, Any]) -> CostExplorerPages:
        pages: list[dict[str, Any]] = []
        request_count = 0
        next_token: str | None = None
        seen_tokens: set[str] = set()

        while True:
            request = dict(query)
            if next_token:
                request["NextPageToken"] = next_token
            try:
                response = self._client.get_cost_and_usage(**request)
            except ClientError as exc:
                raise _map_client_error(exc) from exc
            except BotoCoreError as exc:
                raise AwsBillingUpstreamError(
                    "UPSTREAM_ERROR",
                    "Não foi possível conectar ao AWS Cost Explorer.",
                ) from exc

            request_count += 1
            pages.append(response)
            token = response.get("NextPageToken")
            if not token:
                break
            token = str(token)
            if token in seen_tokens:
                raise AwsBillingUpstreamError(
                    "PAGINATION_ERROR",
                    "O AWS Cost Explorer repetiu um token de paginação.",
                )
            seen_tokens.add(token)
            next_token = token

        return CostExplorerPages(tuple(pages), request_count)
