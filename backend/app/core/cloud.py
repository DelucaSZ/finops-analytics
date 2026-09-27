from enum import StrEnum


class CloudProvider(StrEnum):
    AWS = "aws"
    OCI = "oci"
    AZURE = "azure"
    GCP = "gcp"


PROVIDER_LABELS: dict[CloudProvider, str] = {
    CloudProvider.AWS: "AWS",
    CloudProvider.OCI: "OCI",
    CloudProvider.AZURE: "Azure",
    CloudProvider.GCP: "GCP",
}


def normalize_provider(value: str | CloudProvider) -> str:
    """Return the canonical provider key and reject unknown provider names."""
    return CloudProvider(str(value).strip().lower()).value


def provider_label(value: str | CloudProvider) -> str:
    provider = CloudProvider(normalize_provider(value))
    return PROVIDER_LABELS[provider]
