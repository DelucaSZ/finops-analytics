from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import oci
from requests import exceptions as requests_exceptions

from app.services.oci_auth import OciConnectionSnapshot

DISCOVERY_CONNECT_TIMEOUT_SECONDS = 5
DISCOVERY_READ_TIMEOUT_SECONDS = 30
DISCOVERY_RETRY = oci.retry.DEFAULT_RETRY_STRATEGY


class OciDiscoveryClientConfigurationError(RuntimeError):
    """Raised when the in-memory OCI signing configuration cannot build an SDK client."""


class OciPageFailure(RuntimeError):
    def __init__(self, *, items: list[Any], pages: int, cause: Exception):
        super().__init__("OCI paginated operation failed")
        self.items = items
        self.pages = pages
        self.cause = cause


@dataclass(frozen=True)
class OciPageResult:
    items: list[Any]
    pages: int


@dataclass(frozen=True)
class OciFailureClassification:
    category: str
    message: str
    authentication_fatal: bool = False


def classify_oci_failure(exc: Exception) -> OciFailureClassification:
    if isinstance(exc, oci.exceptions.ServiceError):
        status = int(exc.status or 0)
        if status == 401:
            return OciFailureClassification(
                "authentication_failed",
                "OCI rejected the API signing credentials",
                authentication_fatal=True,
            )
        if status in {403, 404}:
            return OciFailureClassification(
                "authorization_failed",
                "OCI denied access or did not expose the requested resource",
            )
        if status == 429:
            return OciFailureClassification(
                "service_throttled",
                "OCI rate-limited the discovery request",
            )
        if status in {408, 504}:
            return OciFailureClassification(
                "timeout",
                "OCI discovery request timed out",
            )
        if status >= 500:
            return OciFailureClassification(
                "service_unavailable",
                "OCI service is temporarily unavailable",
            )
        return OciFailureClassification(
            "service_error",
            "OCI returned an unexpected service error during discovery",
        )
    if isinstance(
        exc,
        (
            oci.exceptions.ConnectTimeout,
            requests_exceptions.Timeout,
        ),
    ):
        return OciFailureClassification(
            "timeout",
            "OCI discovery request timed out",
        )
    if isinstance(
        exc,
        (
            oci.exceptions.RequestException,
            requests_exceptions.ConnectionError,
        ),
    ):
        return OciFailureClassification(
            "network_error",
            "OCI could not be reached while performing discovery",
        )
    if isinstance(exc, (oci.exceptions.ClientError, TypeError, ValueError)):
        return OciFailureClassification(
            "local_configuration_invalid",
            "OCI SDK rejected the local discovery configuration",
            authentication_fatal=True,
        )
    return OciFailureClassification(
        "unexpected_error",
        "OCI discovery failed unexpectedly",
    )


def list_all_pages(
    call: Callable[..., Any],
    *args: Any,
    item_extractor: Callable[[Any], list[Any]] | None = None,
    **kwargs: Any,
) -> OciPageResult:
    """Consume every OCI page while preserving already-retrieved items on later failure."""
    items: list[Any] = []
    pages = 0
    page: str | None = None
    while True:
        call_kwargs = dict(kwargs)
        if page is not None:
            call_kwargs["page"] = page
        try:
            response = call(*args, **call_kwargs)
        except Exception as exc:
            raise OciPageFailure(items=items, pages=pages, cause=exc) from None

        pages += 1
        data = response.data
        page_items = item_extractor(data) if item_extractor is not None else data
        items.extend(list(page_items or []))
        headers = getattr(response, "headers", {}) or {}
        next_page = headers.get("opc-next-page") or headers.get("Opc-Next-Page")
        if not next_page:
            break
        page = str(next_page)
    return OciPageResult(items=items, pages=pages)


class OciClientFactory:
    """Build and cache OCI SDK clients per service/region for one discovery execution."""

    def __init__(self, snapshot: OciConnectionSnapshot):
        self._snapshot = snapshot
        self._clients: dict[tuple[str, str], Any] = {}

    def _config(self, region: str) -> dict[str, str]:
        config = {
            "tenancy": self._snapshot.tenancy_ocid,
            "user": self._snapshot.user_ocid,
            "fingerprint": self._snapshot.fingerprint,
            "region": region,
            "key_content": self._snapshot.private_key_pem,
        }
        if self._snapshot.private_key_password is not None:
            config["pass_phrase"] = self._snapshot.private_key_password
        return config

    def _get(self, service: str, region: str, constructor: Callable[..., Any]) -> Any:
        key = (service, region)
        existing = self._clients.get(key)
        if existing is not None:
            return existing
        try:
            client = constructor(
                self._config(region),
                timeout=(DISCOVERY_CONNECT_TIMEOUT_SECONDS, DISCOVERY_READ_TIMEOUT_SECONDS),
                retry_strategy=DISCOVERY_RETRY,
            )
        except (oci.exceptions.ClientError, TypeError, ValueError):
            raise OciDiscoveryClientConfigurationError(
                "OCI signing configuration is invalid for discovery"
            ) from None
        self._clients[key] = client
        return client

    def resource_search(self, region: str):
        return self._get("resource_search", region, oci.resource_search.ResourceSearchClient)

    def identity(self, region: str):
        return self._get("identity", region, oci.identity.IdentityClient)

    def compute(self, region: str):
        return self._get("compute", region, oci.core.ComputeClient)

    def blockstorage(self, region: str):
        return self._get("block_storage", region, oci.core.BlockstorageClient)

    def virtual_network(self, region: str):
        return self._get("virtual_network", region, oci.core.VirtualNetworkClient)

    def optimizer(self, region: str):
        return self._get("optimizer", region, oci.optimizer.OptimizerClient)
