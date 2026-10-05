from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider, normalize_provider
from app.models.account import AwsAccount, CloudAccount, OciAccountConfiguration
from app.models.scan import Scan
from app.services.aws_auth import assume_account_session, get_caller_identity
from app.services.collector_types import CollectedFinding
from app.services.collectors import run_collectors
from app.services.oci_analyzers import OciAnalysisService, OciAnalyzerRegistry
from app.services.oci_auth import OciConnectionError
from app.services.oci_cloud_advisor import OciCloudAdvisorService
from app.services.oci_correlation import correlate_oci_datasets
from app.services.oci_credentials import resolve_oci_signing_credentials
from app.services.oci_discovery import OciDiscoveryService
from app.services.oci_monitoring import OciMonitoringService
from app.services.oci_usage import OciUsageService
from app.services.policies import list_effective_policies
from app.services.provider_capabilities import ProviderOperation, require_provider_operation


class CollectionPreconditionError(ValueError):
    """Collection cannot start because an administrative precondition is not satisfied."""


class CollectionExecutorUnavailable(CollectionPreconditionError):
    """No operational collection executor is registered for the provider."""


class ProviderExecutionError(RuntimeError):
    """A provider call failed after collection preconditions were satisfied."""

    def __init__(
        self,
        provider: str,
        cause: Exception,
        *,
        connection_failure: bool = True,
    ):
        self.provider = provider
        self.cause = cause
        self.connection_failure = connection_failure
        super().__init__(str(cause))


@dataclass(frozen=True)
class CollectionPreparation:
    legacy_scan_account_id: int | None
    scope: dict[str, object]


@dataclass(frozen=True)
class CollectionExecutionResult:
    findings: list[CollectedFinding]
    active_rule_keys: list[str]
    collector_errors: list[object]
    resources_analyzed: int = 0


class CollectionExecutor(Protocol):
    provider: str

    def prepare(
        self,
        db: Session,
        account: CloudAccount,
        *,
        scan: Scan | None = None,
    ) -> CollectionPreparation: ...

    def execute(
        self,
        db: Session,
        account: CloudAccount,
        scan: Scan,
    ) -> CollectionExecutionResult: ...

    def mark_connection_success(self, account: CloudAccount) -> None: ...

    def mark_connection_failure(self, account: CloudAccount, error: str) -> None: ...


class AwsCollectionExecutor:
    provider = CloudProvider.AWS.value

    @staticmethod
    def _configuration(
        db: Session,
        account: CloudAccount,
        *,
        scan: Scan | None = None,
    ) -> AwsAccount:
        if account.provider != CloudProvider.AWS.value:
            raise CollectionPreconditionError("AWS executor received a non-AWS CloudAccount")

        aws_account = db.scalar(select(AwsAccount).where(AwsAccount.cloud_account_id == account.id))
        if aws_account is None:
            raise CollectionPreconditionError("AWS operational configuration is missing")
        if aws_account.aws_account_id != account.native_account_id:
            raise CollectionPreconditionError(
                "AWS operational configuration does not match the CloudAccount identity"
            )
        if scan is not None and scan.account_id != aws_account.id:
            raise CollectionPreconditionError(
                "Scan legacy AWS account link does not match its CloudAccount"
            )
        return aws_account

    def prepare(
        self,
        db: Session,
        account: CloudAccount,
        *,
        scan: Scan | None = None,
    ) -> CollectionPreparation:
        aws_account = self._configuration(db, account, scan=scan)
        return CollectionPreparation(
            legacy_scan_account_id=aws_account.id,
            scope={"regions": sorted(aws_account.regions)},
        )

    def execute(
        self,
        db: Session,
        account: CloudAccount,
        scan: Scan,
    ) -> CollectionExecutionResult:
        aws_account = self._configuration(db, account, scan=scan)
        require_provider_operation(account.provider, ProviderOperation.FINOPS_POLICIES)
        policies = list_effective_policies(db, aws_account.id)
        active_rule_keys = [
            policy["rule_key"] for policy in policies if policy["enabled"] and policy["implemented"]
        ]
        expected_account_id = account.native_account_id
        regions = list(aws_account.regions)

        # Release the database transaction before STS and collector network I/O.
        db.expunge(aws_account)
        db.commit()

        try:
            aws_session = assume_account_session(aws_account)
            identity = get_caller_identity(aws_session)
            if identity.account_id != expected_account_id:
                raise RuntimeError(
                    f"Assumed role returned account {identity.account_id}; "
                    f"expected {expected_account_id}"
                )
            findings, collector_errors, failed_rule_keys = run_collectors(
                aws_session, regions, policies
            )
        except Exception as exc:
            raise ProviderExecutionError(self.provider, exc) from exc

        active_rule_keys = [key for key in active_rule_keys if key not in failed_rule_keys]
        return CollectionExecutionResult(
            findings=findings,
            active_rule_keys=active_rule_keys,
            collector_errors=list(collector_errors),
            # The current AWS collectors do not expose the total evaluated resources.
            resources_analyzed=0,
        )

    def mark_connection_success(self, account: CloudAccount) -> None:
        account.connection_status = "connected"
        account.last_error = None

    def mark_connection_failure(self, account: CloudAccount, error: str) -> None:
        account.connection_status = "error"
        account.last_error = error[:2000]


class OciCollectionExecutor:
    provider = CloudProvider.OCI.value
    _CONNECTION_ERROR_TOKENS = (
        "credential",
        "authentication",
        "signing",
        "private key",
        "passphrase",
        "fingerprint",
        "tenancy",
        "local configuration",
    )

    @staticmethod
    def _configuration(
        db: Session,
        account: CloudAccount,
        *,
        scan: Scan | None = None,
    ) -> OciAccountConfiguration:
        if account.provider != CloudProvider.OCI.value:
            raise CollectionPreconditionError("OCI executor received a non-OCI CloudAccount")
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account.id
            )
        )
        if configuration is None:
            raise CollectionPreconditionError("OCI operational configuration is missing")
        if scan is not None and scan.account_id is not None:
            raise CollectionPreconditionError("OCI scan must not reference a legacy AWS account")
        return configuration

    def prepare(
        self,
        db: Session,
        account: CloudAccount,
        *,
        scan: Scan | None = None,
    ) -> CollectionPreparation:
        configuration = self._configuration(db, account, scan=scan)
        regions = configuration.scope_regions or [configuration.region]
        return CollectionPreparation(
            legacy_scan_account_id=None,
            scope={
                "regions": sorted(dict.fromkeys(regions)),
                "compartments": sorted(dict.fromkeys(configuration.compartment_ocids)),
                "include_root_compartment": configuration.include_root_compartment,
                "include_subcompartments": configuration.include_subcompartments,
            },
        )

    @staticmethod
    def _issues(*results) -> list[object]:
        issues: list[object] = []
        for result in results:
            issues.extend(list(getattr(result, "warnings", []) or []))
            issues.extend(list(getattr(result, "errors", []) or []))
        return issues

    @staticmethod
    def _fatal_connection_issue(result) -> bool:
        for issue in list(getattr(result, "errors", []) or []):
            if not bool(getattr(issue, "fatal", False)):
                continue
            category = str(getattr(issue, "category", "")).lower()
            source = str(getattr(issue, "source", "")).lower()
            if any(
                token in category or token in source
                for token in (
                    "credential",
                    "authentication",
                    "local_configuration",
                    "sign",
                )
            ):
                return True
        return False

    @staticmethod
    def _safe_result_message(result, fallback: str) -> str:
        errors = list(getattr(result, "errors", []) or [])
        return str(getattr(errors[0], "message", fallback)) if errors else fallback

    def execute(
        self,
        db: Session,
        account: CloudAccount,
        scan: Scan,
    ) -> CollectionExecutionResult:
        self._configuration(db, account, scan=scan)
        try:
            snapshot = resolve_oci_signing_credentials(db, account.id)
        except OciConnectionError as exc:
            raise ProviderExecutionError(
                self.provider,
                RuntimeError(f"OCI credential failure: {exc.safe_message}"),
                connection_failure=True,
            ) from None
        except Exception as exc:
            raise ProviderExecutionError(
                self.provider,
                RuntimeError("OCI signing credentials could not be resolved"),
                connection_failure=True,
            ) from exc

        if snapshot.tenancy_ocid != account.native_account_id:
            raise ProviderExecutionError(
                self.provider,
                RuntimeError("OCI credential tenancy does not match the CloudAccount identity"),
                connection_failure=True,
            )

        # No ORM object carrying credentials is persisted. Release the transaction before
        # read-only OCI network I/O while retaining only the in-memory, repr-safe snapshot.
        db.commit()

        def cached_credentials(_db, _account_id):
            return snapshot

        try:
            discovery_service = OciDiscoveryService(credential_resolver=cached_credentials)
            discovery = discovery_service.discover(snapshot)
            if discovery.status == "failed":
                connection_failure = self._fatal_connection_issue(discovery)
                message = self._safe_result_message(discovery, "OCI Discovery failed")
                if connection_failure:
                    message = f"OCI authentication failure: {message}"
                raise ProviderExecutionError(
                    self.provider,
                    RuntimeError(message),
                    connection_failure=connection_failure,
                )

            advisor = OciCloudAdvisorService(credential_resolver=cached_credentials).collect(
                snapshot,
                discovery=discovery,
            )
            usage = OciUsageService(credential_resolver=cached_credentials).collect_account(
                db,
                account.id,
                inventory=discovery,
            )
            monitoring_service = OciMonitoringService(credential_resolver=cached_credentials)
            monitoring = monitoring_service.collect_account(
                db,
                account.id,
                inventory=discovery,
            )

            for result, label in (
                (advisor, "OCI Cloud Advisor"),
                (usage, "OCI Usage API"),
                (monitoring, "OCI Monitoring"),
            ):
                if result.status == "failed" and self._fatal_connection_issue(result):
                    message = self._safe_result_message(result, f"{label} authentication failed")
                    raise ProviderExecutionError(
                        self.provider,
                        RuntimeError(f"OCI authentication failure: {message}"),
                        connection_failure=True,
                    )

            correlation = correlate_oci_datasets(discovery, advisor, usage, monitoring)
            registry = OciAnalyzerRegistry()
            findings = OciAnalysisService(registry).analyze(correlation)
        except ProviderExecutionError:
            raise
        except Exception as exc:
            raise ProviderExecutionError(
                self.provider,
                RuntimeError("OCI collection pipeline failed"),
                connection_failure=False,
            ) from exc

        return CollectionExecutionResult(
            findings=findings,
            active_rule_keys=list(registry.rule_keys),
            collector_errors=self._issues(discovery, advisor, usage, monitoring),
            resources_analyzed=len(discovery.resources),
        )

    def mark_connection_success(self, account: CloudAccount) -> None:
        account.connection_status = "connected"
        account.last_error = None

    def mark_connection_failure(self, account: CloudAccount, error: str) -> None:
        lowered = error.lower()
        if not any(token in lowered for token in self._CONNECTION_ERROR_TOKENS):
            return
        account.connection_status = "error"
        account.last_error = error[:2000]


class CollectionExecutorRegistry:
    def __init__(self, executors: tuple[CollectionExecutor, ...]):
        self._executors: dict[str, CollectionExecutor] = {}
        for executor in executors:
            provider = normalize_provider(executor.provider)
            if provider in self._executors:
                raise ValueError(f"Duplicate collection executor for provider {provider}")
            self._executors[provider] = executor

    def get(self, provider: str) -> CollectionExecutor:
        try:
            provider_key = normalize_provider(provider)
        except ValueError as exc:
            raise CollectionExecutorUnavailable(f"Unknown cloud provider: {provider}") from exc
        executor = self._executors.get(provider_key)
        if executor is None:
            raise CollectionExecutorUnavailable(
                f"Provider {provider_key} has no operational collection executor"
            )
        return executor

    def has(self, provider: str) -> bool:
        try:
            self.get(provider)
        except CollectionExecutorUnavailable:
            return False
        return True


COLLECTION_EXECUTORS = CollectionExecutorRegistry(
    (AwsCollectionExecutor(), OciCollectionExecutor())
)


def get_collection_executor(provider: str) -> CollectionExecutor:
    return COLLECTION_EXECUTORS.get(provider)


def has_collection_executor(provider: str) -> bool:
    return COLLECTION_EXECUTORS.has(provider)
