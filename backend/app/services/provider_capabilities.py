from dataclasses import asdict, dataclass
from enum import StrEnum

from app.core.cloud import CloudProvider, normalize_provider, provider_label


class ProviderOperation(StrEnum):
    REGISTRATION = "registration"
    EDITING = "editing"
    CONNECTION_TEST = "connection_test"
    MANUAL_COLLECTION = "manual_collection"
    SCHEDULING = "scheduling"
    FINOPS_POLICIES = "finops_policies"


class UnsupportedProviderOperation(ValueError):
    """Raised when a provider does not implement the requested operation."""


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    label: str
    registration: bool
    editing: bool
    connection_test: bool
    manual_collection: bool
    scheduling: bool
    finops_policies: bool


_CAPABILITIES: dict[str, ProviderCapabilities] = {
    CloudProvider.AWS.value: ProviderCapabilities(
        provider=CloudProvider.AWS.value,
        label=provider_label(CloudProvider.AWS),
        registration=True,
        editing=True,
        connection_test=True,
        manual_collection=True,
        scheduling=True,
        finops_policies=True,
    ),
    CloudProvider.OCI.value: ProviderCapabilities(
        provider=CloudProvider.OCI.value,
        label=provider_label(CloudProvider.OCI),
        registration=True,
        editing=True,
        connection_test=True,
        manual_collection=True,
        scheduling=True,
        finops_policies=False,
    ),
    CloudProvider.AZURE.value: ProviderCapabilities(
        provider=CloudProvider.AZURE.value,
        label=provider_label(CloudProvider.AZURE),
        registration=False,
        editing=False,
        connection_test=False,
        manual_collection=False,
        scheduling=False,
        finops_policies=False,
    ),
    CloudProvider.GCP.value: ProviderCapabilities(
        provider=CloudProvider.GCP.value,
        label=provider_label(CloudProvider.GCP),
        registration=False,
        editing=False,
        connection_test=False,
        manual_collection=False,
        scheduling=False,
        finops_policies=False,
    ),
}


def get_provider_capabilities(provider: str | CloudProvider) -> ProviderCapabilities:
    try:
        provider_key = normalize_provider(provider)
    except ValueError as exc:
        raise UnsupportedProviderOperation(f"Unknown cloud provider: {provider}") from exc
    capabilities = _CAPABILITIES.get(provider_key)
    if capabilities is None:
        raise UnsupportedProviderOperation(f"Unknown cloud provider: {provider_key}")
    return capabilities


def list_provider_capabilities() -> list[dict]:
    return [asdict(_CAPABILITIES[provider.value]) for provider in CloudProvider]


def supports_provider_operation(
    provider: str | CloudProvider,
    operation: ProviderOperation,
) -> bool:
    return bool(getattr(get_provider_capabilities(provider), operation.value))


def require_provider_operation(
    provider: str | CloudProvider,
    operation: ProviderOperation,
) -> ProviderCapabilities:
    capabilities = get_provider_capabilities(provider)
    if not getattr(capabilities, operation.value):
        raise UnsupportedProviderOperation(
            f"Provider {capabilities.label} does not support {operation.value}"
        )
    return capabilities


def providers_supporting(operation: ProviderOperation) -> tuple[str, ...]:
    return tuple(
        capabilities.provider
        for capabilities in _CAPABILITIES.values()
        if getattr(capabilities, operation.value)
    )
