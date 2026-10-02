from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.services.oci_auth import OciConnectionError, OciConnectionSnapshot
from app.services.oci_clients import (
    OciClientFactory,
    OciDiscoveryClientConfigurationError,
    OciPageFailure,
    classify_oci_failure,
    list_all_pages,
)
from app.services.oci_cloud_advisor_models import (
    OciCloudAdvisorIssue,
    OciCloudAdvisorResult,
    OciNativeRecommendation,
    OciNativeResourceAction,
)
from app.services.oci_credentials import resolve_oci_signing_credentials
from app.services.oci_discovery_models import OciDiscoveryIssue, OciDiscoveryResult
from app.services.oci_discovery_operations import OciDiscoveryOperations, OciFatalDiscoveryAbort
from app.services.oci_scope import resolve_oci_discovery_scope

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _items(data: Any) -> list[Any]:
    return list(getattr(data, "items", []) or [])


def _safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        lowered = key.lower()
        secret_tokens = ("credential", "private", "passphrase", "signer", "key_content")
        if any(token in lowered for token in secret_tokens):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            allowed[key] = item
        elif isinstance(item, dict):
            allowed[key] = {
                str(child_key): child_value
                for child_key, child_value in item.items()
                if isinstance(child_value, (str, int, float, bool)) or child_value is None
            }
    return allowed


def _action(value: Any) -> dict[str, Any] | str | None:
    if value is None or isinstance(value, str):
        return value
    result = {
        key: getattr(value, key, None)
        for key in ("type", "description", "url")
        if getattr(value, key, None) is not None
    }
    return result or None


class OciCloudAdvisorService:
    """Read-only Cloud Advisor acquisition layer. It never executes OCI recommendations."""

    def __init__(
        self,
        *,
        credential_resolver: Callable[[Session, int], OciConnectionSnapshot] | None = None,
        client_factory_cls: type[OciClientFactory] = OciClientFactory,
    ) -> None:
        self._credential_resolver = credential_resolver or resolve_oci_signing_credentials
        self._client_factory_cls = client_factory_cls

    def collect_account(
        self,
        db: Session,
        cloud_account_id: int,
        *,
        discovery: OciDiscoveryResult | None = None,
    ) -> OciCloudAdvisorResult:
        started_at = _now()
        try:
            snapshot = self._credential_resolver(db, cloud_account_id)
        except OciConnectionError as exc:
            return self._failed(
                started_at,
                OciCloudAdvisorIssue(
                    category=exc.internal_code or exc.code,
                    source="credentials",
                    operation="resolve_signing_credentials",
                    message=exc.safe_message,
                    fatal=True,
                ),
            )
        except Exception:
            return self._failed(
                started_at,
                OciCloudAdvisorIssue(
                    category="credential_resolution_failed",
                    source="credentials",
                    operation="resolve_signing_credentials",
                    message="OCI signing credentials could not be resolved",
                    fatal=True,
                ),
            )
        return self.collect(snapshot, discovery=discovery, started_at=started_at)

    def collect(
        self,
        snapshot: OciConnectionSnapshot,
        *,
        discovery: OciDiscoveryResult | None = None,
        started_at: datetime | None = None,
    ) -> OciCloudAdvisorResult:
        started_at = started_at or _now()
        warnings: list[OciCloudAdvisorIssue] = []
        errors: list[OciCloudAdvisorIssue] = []
        pages = {"recommendations": 0, "resource_actions": 0}
        recommendations: dict[str, OciNativeRecommendation] = {}
        actions: dict[str, OciNativeResourceAction] = {}
        recommendation_complete = True
        action_complete = True

        try:
            factory = self._client_factory_cls(snapshot)
            scope = self._resolve_scope(snapshot, factory, errors)
            if not scope.compartment_ids:
                return self._result(
                    status="partial" if errors else "success",
                    recommendations=[],
                    actions=[],
                    recommendation_complete=not errors,
                    action_complete=not errors,
                    warnings=warnings,
                    errors=errors,
                    pages=pages,
                    started_at=started_at,
                )

            optimizer = factory.optimizer(scope.regions[0] if scope.regions else snapshot.region)
            targets = self._query_targets(snapshot, scope.compartment_ids)
            for compartment_id, in_subtree in targets:
                listed, ok, count_pages = self._paged(
                    snapshot,
                    call=optimizer.list_recommendations,
                    source="cloud_advisor",
                    operation="list_recommendations",
                    compartment_id=compartment_id,
                    kwargs={
                        "compartment_id": compartment_id,
                        "compartment_id_in_subtree": in_subtree,
                    },
                    errors=errors,
                )
                pages["recommendations"] += count_pages
                recommendation_complete = recommendation_complete and ok
                for item in listed:
                    normalized = self._recommendation(item)
                    if normalized is not None:
                        recommendations.setdefault(normalized.recommendation_id, normalized)

                listed_actions, ok, count_pages = self._paged(
                    snapshot,
                    call=optimizer.list_resource_actions,
                    source="cloud_advisor",
                    operation="list_resource_actions",
                    compartment_id=compartment_id,
                    kwargs={
                        "compartment_id": compartment_id,
                        "compartment_id_in_subtree": in_subtree,
                        "include_resource_metadata": True,
                    },
                    errors=errors,
                )
                pages["resource_actions"] += count_pages
                action_complete = action_complete and ok
                for item in listed_actions:
                    normalized = self._resource_action(item)
                    if normalized is not None:
                        actions.setdefault(normalized.resource_action_id, normalized)

        except OciFatalDiscoveryAbort as exc:
            errors.append(self._from_discovery_issue(exc.issue))
            return self._result(
                status="failed",
                recommendations=list(recommendations.values()),
                actions=list(actions.values()),
                recommendation_complete=False,
                action_complete=False,
                warnings=warnings,
                errors=errors,
                pages=pages,
                started_at=started_at,
            )
        except OciDiscoveryClientConfigurationError:
            return self._failed(
                started_at,
                OciCloudAdvisorIssue(
                    category="local_configuration_invalid",
                    source="client_factory",
                    operation="build_optimizer_client",
                    message="OCI signing configuration is invalid for Cloud Advisor",
                    fatal=True,
                ),
            )

        allowed_compartments = set(scope.compartment_ids)
        allowed_regions = set(scope.regions)
        inventory_ids = (
            {resource.resource_id for resource in discovery.resources}
            if discovery is not None
            else None
        )
        for action in actions.values():
            action.scope_match = self._scope_match(
                action,
                allowed_compartments=allowed_compartments,
                allowed_regions=allowed_regions,
            )
            if action.resource_id is not None and inventory_ids is not None:
                action.inventory_match = action.resource_id in inventory_ids
                if not action.inventory_match:
                    warnings.append(
                        OciCloudAdvisorIssue(
                            category="resource_not_in_discovery_inventory",
                            source="cloud_advisor",
                            operation="correlate_inventory",
                            message=(
                                "Cloud Advisor resource was not found in the provided "
                                "Discovery inventory"
                            ),
                            compartment_id=action.compartment_id,
                        )
                    )
            if action.scope_match == "unknown":
                warnings.append(
                    OciCloudAdvisorIssue(
                        category="scope_unknown",
                        source="cloud_advisor",
                        operation="scope_resource_action",
                        message=(
                            "Cloud Advisor resource action lacks enough metadata to "
                            "determine configured scope"
                        ),
                        compartment_id=action.compartment_id,
                    )
                )

        action_by_recommendation: dict[str, list[OciNativeResourceAction]] = {}
        for action in actions.values():
            if action.recommendation_id:
                action_by_recommendation.setdefault(action.recommendation_id, []).append(action)

        kept_actions = [action for action in actions.values() if action.scope_match != "outside"]
        kept_recommendations: list[OciNativeRecommendation] = []
        for recommendation in recommendations.values():
            related = action_by_recommendation.get(recommendation.recommendation_id, [])
            if related:
                if any(action.scope_match == "inside" for action in related):
                    recommendation.scope_match = "inside"
                elif all(action.scope_match == "outside" for action in related):
                    recommendation.scope_match = "outside"
                else:
                    recommendation.scope_match = "unknown"
            else:
                recommendation.scope_match = "unknown"
                warnings.append(
                    OciCloudAdvisorIssue(
                        category="scope_unknown",
                        source="cloud_advisor",
                        operation="scope_recommendation",
                        message=(
                            "Cloud Advisor recommendation has no resource action metadata "
                            "for scope evaluation"
                        ),
                    )
                )
            if recommendation.scope_match != "outside":
                kept_recommendations.append(recommendation)

        status = (
            "partial"
            if errors or not recommendation_complete or not action_complete
            else "success"
        )
        return self._result(
            status=status,
            recommendations=kept_recommendations,
            actions=kept_actions,
            recommendation_complete=recommendation_complete,
            action_complete=action_complete,
            warnings=warnings,
            errors=errors,
            pages=pages,
            started_at=started_at,
        )

    @staticmethod
    def _resolve_scope(snapshot, factory, errors):
        discovery_errors: list[OciDiscoveryIssue] = []
        operations = OciDiscoveryOperations(snapshot, discovery_errors)
        scope = resolve_oci_discovery_scope(snapshot, factory, operations)
        errors.extend(
            OciCloudAdvisorService._from_discovery_issue(item) for item in discovery_errors
        )
        return scope

    @staticmethod
    def _query_targets(snapshot: OciConnectionSnapshot, compartment_ids: tuple[str, ...]):
        if (
            snapshot.include_root_compartment
            and snapshot.include_subcompartments
            and snapshot.tenancy_ocid in compartment_ids
        ):
            return [(snapshot.tenancy_ocid, True)]
        return [(compartment_id, False) for compartment_id in compartment_ids]

    @staticmethod
    def _paged(
        snapshot,
        *,
        call,
        source,
        operation,
        compartment_id,
        kwargs,
        errors,
    ):
        started = perf_counter()
        try:
            result = list_all_pages(call, item_extractor=_items, **kwargs)
            logger.info(
                "OCI Cloud Advisor cloud_account_id=%s provider=oci operation=%s "
                "compartment_id=%s count=%s pages=%s duration_ms=%s status=success",
                snapshot.cloud_account_id,
                operation,
                compartment_id,
                len(result.items),
                result.pages,
                round((perf_counter() - started) * 1000),
            )
            return result.items, True, result.pages
        except OciPageFailure as exc:
            classification = classify_oci_failure(exc.cause)
            issue = OciCloudAdvisorIssue(
                category=classification.category,
                source=source,
                operation=operation,
                message=classification.message,
                compartment_id=compartment_id,
                fatal=classification.authentication_fatal,
            )
            if classification.authentication_fatal:
                raise OciFatalDiscoveryAbort(
                    OciDiscoveryIssue(
                        category=issue.category,
                        source=issue.source,
                        operation=issue.operation,
                        message=issue.message,
                        compartment_id=issue.compartment_id,
                        fatal=True,
                    )
                ) from None
            errors.append(issue)
            logger.info(
                "OCI Cloud Advisor cloud_account_id=%s provider=oci operation=%s "
                "compartment_id=%s count=%s pages=%s duration_ms=%s status=partial "
                "error_category=%s",
                snapshot.cloud_account_id,
                operation,
                compartment_id,
                len(exc.items),
                exc.pages,
                round((perf_counter() - started) * 1000),
                classification.category,
            )
            return exc.items, False, exc.pages

    @staticmethod
    def _recommendation(item: Any) -> OciNativeRecommendation | None:
        recommendation_id = getattr(item, "id", None)
        if not recommendation_id:
            return None
        return OciNativeRecommendation(
            recommendation_id=recommendation_id,
            name=getattr(item, "name", None),
            description=getattr(item, "description", None),
            category_id=getattr(item, "category_id", None),
            importance=getattr(item, "importance", None),
            lifecycle_state=getattr(item, "lifecycle_state", None),
            status=getattr(item, "status", None),
            tenancy_id=getattr(item, "compartment_id", None),
            native_estimated_savings=getattr(item, "estimated_cost_saving", None),
            currency=None,
            time_created=getattr(item, "time_created", None),
            time_updated=getattr(item, "time_updated", None),
            time_status_begin=getattr(item, "time_status_begin", None),
            time_status_end=getattr(item, "time_status_end", None),
            raw_metadata=_safe_metadata(getattr(item, "extended_metadata", None)),
        )

    @staticmethod
    def _resource_action(item: Any) -> OciNativeResourceAction | None:
        action_id = getattr(item, "id", None)
        if not action_id:
            return None
        metadata = _safe_metadata(getattr(item, "metadata", None))
        metadata.update(_safe_metadata(getattr(item, "extended_metadata", None)))
        return OciNativeResourceAction(
            resource_action_id=action_id,
            recommendation_id=getattr(item, "recommendation_id", None),
            name=getattr(item, "name", None),
            resource_id=getattr(item, "resource_id", None),
            resource_type=getattr(item, "resource_type", None),
            compartment_id=getattr(item, "compartment_id", None),
            compartment_name=getattr(item, "compartment_name", None),
            action=_action(getattr(item, "action", None)),
            lifecycle_state=getattr(item, "lifecycle_state", None),
            status=getattr(item, "status", None),
            native_estimated_savings=getattr(item, "estimated_cost_saving", None),
            currency=None,
            time_created=getattr(item, "time_created", None),
            time_updated=getattr(item, "time_updated", None),
            time_status_begin=getattr(item, "time_status_begin", None),
            time_status_end=getattr(item, "time_status_end", None),
            raw_metadata=metadata,
        )

    @staticmethod
    def _scope_match(action, *, allowed_compartments, allowed_regions):
        if action.compartment_id and action.compartment_id not in allowed_compartments:
            return "outside"
        region = action.raw_metadata.get("region") or action.raw_metadata.get("Region")
        if region and allowed_regions and region not in allowed_regions:
            return "outside"
        if action.compartment_id in allowed_compartments and (
            not region or region in allowed_regions
        ):
            return "inside"
        return "unknown"

    @staticmethod
    def _from_discovery_issue(issue: OciDiscoveryIssue) -> OciCloudAdvisorIssue:
        return OciCloudAdvisorIssue(
            category=issue.category,
            source=issue.source,
            operation=issue.operation,
            message=issue.message,
            compartment_id=issue.compartment_id,
            region=issue.region,
            fatal=issue.fatal,
        )

    @staticmethod
    def _failed(started_at, issue):
        return OciCloudAdvisorService._result(
            status="failed",
            recommendations=[],
            actions=[],
            recommendation_complete=False,
            action_complete=False,
            warnings=[],
            errors=[issue],
            pages={"recommendations": 0, "resource_actions": 0},
            started_at=started_at,
        )

    @staticmethod
    def _result(
        *,
        status,
        recommendations,
        actions,
        recommendation_complete,
        action_complete,
        warnings,
        errors,
        pages,
        started_at,
    ):
        return OciCloudAdvisorResult(
            status=status,
            recommendations=sorted(recommendations, key=lambda item: item.recommendation_id),
            resource_actions=sorted(actions, key=lambda item: item.resource_action_id),
            recommendation_count=len(recommendations) if recommendation_complete else None,
            resource_action_count=len(actions) if action_complete else None,
            warnings=warnings,
            errors=errors,
            started_at=started_at,
            completed_at=_now(),
            coverage={
                "recommendations": recommendation_complete,
                "resource_actions": action_complete,
            },
            pages=pages,
        )
