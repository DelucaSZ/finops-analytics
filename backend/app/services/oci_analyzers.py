from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.services.collector_types import CollectedFinding
from app.services.oci_correlation_models import (
    OciCorrelationResult,
    OciResourceAnalysisContext,
)
from app.services.oci_pricing import InvalidOciPricingInputError, OciPricingService

ANALYZER_VERSION = "1.0"
RULE_BLOCK_VOLUME_UNATTACHED = "oci_block_volume_unattached"
RULE_PUBLIC_IP_UNASSIGNED = "oci_public_ip_unassigned"
RULE_STOPPED_COMPUTE_WITH_STORAGE = "oci_stopped_compute_with_storage"
RULE_UNTAGGED_RESOURCE = "oci_untagged_resource"

_SUPPORTED_TAG_TYPES = {
    "compute_instance": "compute_api",
    "block_volume": "block_storage_api",
    "boot_volume": "block_storage_api",
    "public_ip": "virtual_network_api",
}
_TERMINAL_STATES = {"TERMINATED", "TERMINATING", "DELETED"}
_OCI_PRICING = OciPricingService()


class OciAnalyzer(Protocol):
    rule_key: str

    def applies_to(self, context: OciResourceAnalysisContext) -> bool: ...

    def analyze(self, context: OciResourceAnalysisContext) -> list[CollectedFinding]: ...


def _inventory_complete(context: OciResourceAnalysisContext, *resource_types: str) -> bool:
    if context.coverage.get("inventory") != "complete":
        return False
    return all(
        context.inventory_coverage.get(resource_type) == "complete"
        for resource_type in resource_types
    )


def _authoritative_inventory(context: OciResourceAnalysisContext, source: str) -> bool:
    return context.inventory is not None and source in context.inventory.sources


def _cost_evidence(context: OciResourceAnalysisContext) -> dict[str, Any]:
    totals = [
        {"currency": currency, "observed_cost": str(value)}
        for currency, value in sorted(context.usage.totals_by_currency.items())
    ]
    return {
        "source": "oci_usage_api",
        "available": bool(totals),
        "period_start": (
            context.usage.period_start.isoformat() if context.usage.period_start else None
        ),
        "period_end": context.usage.period_end.isoformat() if context.usage.period_end else None,
        "totals_by_currency": totals,
        "direct_resource_attribution": bool(context.usage.records),
    }


def _native_recommendations(context: OciResourceAnalysisContext) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for link in context.native_recommendations:
        recommendation = link.recommendation
        rendered.append(
            {
                "source": "oci_cloud_advisor",
                "resource_action_id": link.action.resource_action_id,
                "recommendation_id": (
                    recommendation.recommendation_id
                    if recommendation is not None
                    else link.action.recommendation_id
                ),
                "name": recommendation.name if recommendation is not None else link.action.name,
                "category_id": recommendation.category_id if recommendation is not None else None,
                "status": (
                    recommendation.status if recommendation is not None else link.action.status
                ),
                "native_estimated_savings": (
                    recommendation.native_estimated_savings
                    if recommendation is not None
                    else link.action.native_estimated_savings
                ),
                "currency": (
                    recommendation.currency if recommendation is not None else link.action.currency
                ),
            }
        )
    return sorted(
        rendered,
        key=lambda item: (
            str(item.get("recommendation_id") or ""),
            str(item.get("resource_action_id") or ""),
            str(item.get("name") or ""),
        ),
    )


def _base_evidence(context: OciResourceAnalysisContext) -> dict[str, Any]:
    inventory = context.inventory
    return {
        "analysis_source": "deepops",
        "analyzer_version": ANALYZER_VERSION,
        "coverage": {
            "inventory": context.coverage.get("inventory", "unknown"),
            "inventory_by_type": dict(sorted(context.inventory_coverage.items())),
            "relationships": dict(sorted(context.relationship_coverage.items())),
        },
        "provenance": {key: list(values) for key, values in sorted(context.provenance.items())},
        "inventory": {
            "resource_id": context.resource_id,
            "resource_type": context.resource_type,
            "lifecycle_state": context.lifecycle_state,
            "region": context.region,
            "compartment_id": context.compartment_id,
            "sources": sorted(inventory.sources) if inventory is not None else [],
        },
        "observed_cost": _cost_evidence(context),
        "native_recommendations": _native_recommendations(context),
    }


def _finding(
    context: OciResourceAnalysisContext,
    *,
    rule_key: str,
    service: str,
    title: str,
    description: str,
    recommendation: str,
    severity: str,
    analysis: dict[str, Any],
    current_monthly_cost: Decimal | None = None,
    estimated_monthly_savings: Decimal | None = None,
    currency: str | None = None,
    financial_value_populated: bool = False,
    pricing_evidence: dict[str, Any] | None = None,
) -> CollectedFinding:
    evidence = _base_evidence(context)
    evidence["rule_key"] = rule_key
    evidence["analysis"] = analysis
    evidence["recommendation"] = recommendation
    if pricing_evidence is not None:
        evidence["pricing"] = pricing_evidence
    resolved_currency = currency or (
        next(iter(context.usage.totals_by_currency))
        if len(context.usage.totals_by_currency) == 1
        else "USD"
    )
    return CollectedFinding(
        rule_key=rule_key,
        service=service,
        region=context.region,
        resource_id=context.resource_id,
        resource_name=context.name,
        resource_type=context.resource_type,
        provider_metadata={
            "provider": "oci",
            "compartment_id": context.compartment_id,
            "analyzer_version": ANALYZER_VERSION,
            "analysis_source": "deepops",
            "financial_value_populated": financial_value_populated,
        },
        title=title,
        description=description,
        evidence=evidence,
        current_monthly_cost=(
            current_monthly_cost if current_monthly_cost is not None else Decimal("0")
        ),
        estimated_monthly_savings=(
            estimated_monthly_savings if estimated_monthly_savings is not None else Decimal("0")
        ),
        currency=resolved_currency,
        confidence="high",
        severity=severity,
    )


def _block_volume_pricing(
    attributes: dict[str, Any],
) -> tuple[Decimal, str, bool, dict[str, Any]]:
    size_gb = attributes.get("size_in_gbs")
    vpus_per_gb = attributes.get("vpus_per_gb")
    metadata = _OCI_PRICING.metadata
    missing_fields = [
        field
        for field, value in (("size_in_gbs", size_gb), ("vpus_per_gb", vpus_per_gb))
        if value is None
    ]

    try:
        monthly_cost = _OCI_PRICING.block_volume_monthly_cost(
            size_gb=size_gb,
            vpus_per_gb=vpus_per_gb,
        )
    except InvalidOciPricingInputError:
        pricing_evidence: dict[str, Any] = {
            "status": "missing_pricing_input" if missing_fields else "invalid_pricing_input",
            "source": metadata.source,
            "version": metadata.version,
            "currency": metadata.currency,
            "resource_type": "block_volume",
            "size_gb": size_gb,
            "vpus_per_gb": vpus_per_gb,
            "financial_value_populated": False,
        }
        if missing_fields:
            pricing_evidence["missing_fields"] = missing_fields
        return Decimal("0"), metadata.currency, False, pricing_evidence

    return (
        monthly_cost,
        metadata.currency,
        True,
        {
            "status": "priced",
            "source": metadata.source,
            "version": metadata.version,
            "currency": metadata.currency,
            "resource_type": "block_volume",
            "size_gb": size_gb,
            "vpus_per_gb": vpus_per_gb,
            "monthly_cost": str(monthly_cost),
            "financial_value_populated": True,
        },
    )


@dataclass(frozen=True)
class OciBlockVolumeUnattachedAnalyzer:
    rule_key: str = RULE_BLOCK_VOLUME_UNATTACHED

    def applies_to(self, context: OciResourceAnalysisContext) -> bool:
        return context.resource_type == "block_volume"

    def analyze(self, context: OciResourceAnalysisContext) -> list[CollectedFinding]:
        if not self.applies_to(context) or context.inventory is None:
            return []
        if not _inventory_complete(context, "block_volume"):
            return []
        if not _authoritative_inventory(context, "block_storage_api"):
            return []
        lifecycle = str(context.lifecycle_state or "").upper()
        if lifecycle in _TERMINAL_STATES or lifecycle != "AVAILABLE":
            return []
        attributes = context.inventory.attributes
        if attributes.get("attachment_coverage") != "complete":
            return []
        if attributes.get("attachment_count") != 0:
            return []

        monthly_cost, currency, financial_value_populated, pricing_evidence = (
            _block_volume_pricing(attributes)
        )
        finding = _finding(
            context,
            rule_key=self.rule_key,
            service="OCI Block Storage",
            title="Block Volume OCI sem attachment",
            description=(
                "O Block Volume está disponível e a coleta confirmou que não há attachments ativos."
            ),
            recommendation=(
                "Validar a necessidade do volume e, se não houver dependência operacional ou "
                "requisito de retenção, considerar remoção após os controles de backup aplicáveis."
            ),
            severity="medium",
            analysis={
                "attachment_count": 0,
                "attachment_coverage": "complete",
                "size_in_gbs": attributes.get("size_in_gbs"),
                "vpus_per_gb": attributes.get("vpus_per_gb"),
            },
            current_monthly_cost=monthly_cost,
            estimated_monthly_savings=monthly_cost,
            currency=currency,
            financial_value_populated=financial_value_populated,
            pricing_evidence=pricing_evidence,
        )
        return [finding]


@dataclass(frozen=True)
class OciPublicIpUnassignedAnalyzer:
    rule_key: str = RULE_PUBLIC_IP_UNASSIGNED

    def applies_to(self, context: OciResourceAnalysisContext) -> bool:
        return context.resource_type == "public_ip"

    def analyze(self, context: OciResourceAnalysisContext) -> list[CollectedFinding]:
        if not self.applies_to(context) or context.inventory is None:
            return []
        if not _inventory_complete(context, "public_ip"):
            return []
        if not _authoritative_inventory(context, "virtual_network_api"):
            return []
        lifecycle = str(context.lifecycle_state or "").upper()
        if lifecycle in _TERMINAL_STATES:
            return []
        attributes = context.inventory.attributes
        if str(attributes.get("lifetime") or "").upper() != "RESERVED":
            return []
        if attributes.get("is_associated") is not False:
            return []

        finding = _finding(
            context,
            rule_key=self.rule_key,
            service="OCI Networking",
            title="Public IP reservado OCI sem associação",
            description=(
                "O Public IP é reservado e a coleta confirmou que ele não está "
                "associado a uma entidade."
            ),
            recommendation=(
                "Validar a necessidade do Public IP reservado sem associação e liberá-lo caso "
                "não seja mais necessário."
            ),
            severity="low",
            analysis={
                "lifetime": attributes.get("lifetime"),
                "is_associated": False,
                "assigned_entity_id": None,
            },
        )
        return [finding]


@dataclass(frozen=True)
class OciStoppedComputeWithStorageAnalyzer:
    rule_key: str = RULE_STOPPED_COMPUTE_WITH_STORAGE

    def applies_to(self, context: OciResourceAnalysisContext) -> bool:
        return context.resource_type == "compute_instance"

    def analyze(self, context: OciResourceAnalysisContext) -> list[CollectedFinding]:
        if not self.applies_to(context) or context.inventory is None:
            return []
        if not _inventory_complete(
            context,
            "compute_instance",
            "block_volume",
            "boot_volume",
        ):
            return []
        if any(
            context.relationship_coverage.get(relation_type) != "complete"
            for relation_type in ("volume_attachment", "boot_volume_attachment")
        ):
            return []
        if not _authoritative_inventory(context, "compute_api"):
            return []
        if str(context.lifecycle_state or "").upper() != "STOPPED":
            return []

        boot_ids: set[str] = set()
        block_ids: set[str] = set()
        for relationship in context.relationships:
            if relationship.target_id != context.resource_id:
                continue
            if (
                relationship.relation_type == "boot_volume_attachment"
                and relationship.source_type == "boot_volume"
                and relationship.target_type == "compute_instance"
            ):
                boot_ids.add(relationship.source_id)
            elif (
                relationship.relation_type == "volume_attachment"
                and relationship.source_type == "block_volume"
                and relationship.target_type == "compute_instance"
            ):
                block_ids.add(relationship.source_id)

        if not boot_ids and not block_ids:
            return []

        finding = _finding(
            context,
            rule_key=self.rule_key,
            service="OCI Compute",
            title="Compute OCI parado mantendo storage persistente",
            description=(
                "A instância está parada, mas mantém storage persistente associado que pode "
                "continuar gerando custo."
            ),
            recommendation=(
                "Validar a necessidade de retenção da instância e considerar descomissionamento "
                "dos recursos persistentes que não forem mais necessários."
            ),
            severity="medium",
            analysis={
                "compute_state": "STOPPED",
                "boot_volume_count": len(boot_ids),
                "block_volume_count": len(block_ids),
                "boot_volume_ids": sorted(boot_ids),
                "block_volume_ids": sorted(block_ids),
            },
        )
        return [finding]


@dataclass(frozen=True)
class OciUntaggedResourceAnalyzer:
    rule_key: str = RULE_UNTAGGED_RESOURCE

    def applies_to(self, context: OciResourceAnalysisContext) -> bool:
        return context.resource_type in _SUPPORTED_TAG_TYPES

    def analyze(self, context: OciResourceAnalysisContext) -> list[CollectedFinding]:
        if not self.applies_to(context) or context.inventory is None:
            return []
        resource_type = context.resource_type
        assert resource_type is not None
        if not _inventory_complete(context, resource_type):
            return []
        if not _authoritative_inventory(context, _SUPPORTED_TAG_TYPES[resource_type]):
            return []
        if context.inventory.freeform_tags or context.inventory.defined_tags:
            return []

        finding = _finding(
            context,
            rule_key=self.rule_key,
            service="OCI Governance",
            title="Recurso OCI sem tags",
            description=(
                "O recurso suportado não possui freeform tags nem defined tags no "
                "inventário coletado."
            ),
            recommendation=(
                "Adicionar metadados de governança e custo conforme a política da organização."
            ),
            severity="low",
            analysis={
                "freeform_tag_count": 0,
                "defined_tag_namespace_count": 0,
                "defined_tag_namespaces": [],
            },
        )
        return [finding]


class OciAnalyzerRegistry:
    def __init__(self, analyzers: list[OciAnalyzer] | None = None) -> None:
        self._analyzers: tuple[OciAnalyzer, ...] = tuple(
            analyzers
            or [
                OciBlockVolumeUnattachedAnalyzer(),
                OciPublicIpUnassignedAnalyzer(),
                OciStoppedComputeWithStorageAnalyzer(),
                OciUntaggedResourceAnalyzer(),
            ]
        )

    @property
    def rule_keys(self) -> tuple[str, ...]:
        return tuple(sorted(analyzer.rule_key for analyzer in self._analyzers))

    def analyze(self, context: OciResourceAnalysisContext) -> list[CollectedFinding]:
        findings: dict[tuple[str, str], CollectedFinding] = {}
        for analyzer in self._analyzers:
            if not analyzer.applies_to(context):
                continue
            for finding in analyzer.analyze(context):
                findings[(finding.rule_key, finding.resource_id)] = finding
        return [findings[key] for key in sorted(findings)]


class OciAnalysisService:
    def __init__(self, registry: OciAnalyzerRegistry | None = None) -> None:
        self._registry = registry or OciAnalyzerRegistry()

    def analyze(self, correlation: OciCorrelationResult) -> list[CollectedFinding]:
        findings: dict[tuple[str, str], CollectedFinding] = {}
        for context in sorted(correlation.resource_contexts, key=lambda item: item.resource_id):
            for finding in self._registry.analyze(context):
                findings[(finding.rule_key, finding.resource_id)] = finding
        return [findings[key] for key in sorted(findings)]
