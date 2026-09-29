import re
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


def validate_native_account_id(provider: str | CloudProvider, value: str) -> str:
    """Validate a provider-native account identifier without changing its case."""
    provider_key = normalize_provider(provider)
    if value != value.strip():
        raise ValueError("Native account identifier must not contain surrounding whitespace")
    if not value or len(value) > 255:
        raise ValueError("Native account identifier must contain between 1 and 255 characters")
    if provider_key == CloudProvider.AWS.value and not re.fullmatch(r"[0-9]{12}", value):
        raise ValueError("AWS account identifier must contain exactly 12 digits")
    if provider_key == CloudProvider.OCI.value and not value.startswith("ocid1."):
        raise ValueError("OCI account identifier must be an OCID")
    return value


def provider_label(value: str | CloudProvider) -> str:
    provider = CloudProvider(normalize_provider(value))
    return PROVIDER_LABELS[provider]
