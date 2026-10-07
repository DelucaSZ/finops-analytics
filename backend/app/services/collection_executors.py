import logging
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider, normalize_provider
from app.models.account import AwsAccount, CloudAccount, OciAccountConfiguration
from app.models.collection_run import CollectionRun
from app.models.scan import Scan
from app.services.aws_auth import assume_account_session, get_caller_identity
from app.services.collection_errors import classify_collection_error
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

logger = logging.getLogger("deepops.collection_executor")


class CollectionPreconditionError(ValueError):
    """Collection cannot start because an administrative precondition is not satisfied."""


class CollectionExecutorUnavailable(CollectionPreconditionError):
    """No operational collection executor is registered for the provider."""


class ProviderExecutionError(RuntimeError):
    """A provider-stage failure with safe, operational metadata."""

    def __init__(
        self,
        provider: str,
        cause: Exception,
        *,
        connection_failure: bool = False,
        stage: str = "provider",
        category: str | None = None,
        retryable: bool | None = None,
    ):
        info = classify_collection_error(cause)
        self.provider = provider
        self.cause = cause
        self.connection_failure = connection_failure
        self.stage = stage
        self.category = category or info.category
        self.retryable = info.retryable if retryable is None else retryable
        self.public_message = info.public_message
        # Never copy a raw SDK/database exception into the exception string. The
        # original cause is preserved through exception chaining for technical logs.
        super().__init__(self.public_message)


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


def _cache_run_id(db: Session, scan: Scan) -> str:
    cached = getattr(scan, "_operational_collection_run_id", None)
    if cached is not None:
        return cached
    run_id = db.scalar(select(CollectionRun.id).where(CollectionRun.scan_id == scan.id))
    cached = run_id or "missing"
    scan._operational_collection_run_id = cached
    return cached


def _run_id(db: Session, scan: Scan) -> str:
    cached = getattr(scan, "_operational_collection_run_id", None)
    return cached if cached is not None else _cache_run_id(db, scan)


def _log_stage(
    db: Session,
    account: CloudAccount,
    scan: Scan,
    *,
    event: str,
    stage: str,
    duration_ms: int | None = None,
    resource_count: int | None = None,
    warning_count: int | None = None,
    error: Exception | object | None = None,
) -> None:
    suffix: list[str] = []
    if duration_ms is not None:
        suffix.append(f"duration_ms={duration_ms}")
    if resource_count is not None:
        suffix.append(f"resource_count={resource_count}")
    if warning_count is not None:
        suffix.append(f"warning_count={warning_count}")
    if error is not None:
        info = classify_collection_error(error)
        retryable = str(info.retryable).lower() if info.retryable is not None else "unknown"
        suffix.extend(
            (
                f"error_category={info.category}",
                f"retryable={retryable}",
                f"error={info.public_message}",
            )
        )
    details = " " + " ".join(suffix) if suffix else ""
    logger.info(
        "event=%s provider=%s cloud_account_id=%s native_account_id=%s scan_id=%s "
        "collection_run_id=%s trigger=%s executor=%s stage=%s%s",
        event,
        account.provider,
        account.id,
        account.native_account_id,
        scan.id,
        _run_id(db, scan),
        scan.trigger,
        type(get_collection_executor(account.provider)).__name__,
        stage,
        details,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


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
    _CONNECTION_ERROR_TOKENS = (
        "credencial",
        "expiredtoken",
        "invalidclienttokenid",
        "signaturedoesnotmatch",
        "authentication",
        "identidade aws",
        "accessdenied",
        "acesso negado",
    )

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

        # Cache correlation data while the setup transaction is already open, then
        # detach loaded ORM rows so logging cannot reopen a transaction before cloud I/O.
        _cache_run_id(db, scan)
        db.expunge(aws_account)
        db.expunge(account)
        db.expunge(scan)
        db.commit()

        auth_started = time.monotonic()
        _log_stage(db, account, scan, event="collection_stage_started", stage="credentials")
        try:
            aws_session = assume_account_session(aws_account)
            identity = get_caller_identity(aws_session)
            if identity.account_id != expected_account_id:
                raise RuntimeError("A identidade AWS não corresponde à conta configurada")
        except Exception as exc:
            info = classify_collection_error(exc)
            connection_failure = info.category in {"authentication", "authorization"}
            if "identidade aws" in str(exc).lower():
                info = classify_collection_error(RuntimeError("InvalidClientTokenId"))
                connection_failure = True
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_failed",
                stage="credentials",
                duration_ms=_elapsed_ms(auth_started),
                error=exc,
            )
            raise ProviderExecutionError(
                self.provider,
                exc,
                connection_failure=connection_failure,
                stage="credentials",
                category=info.category,
                retryable=info.retryable,
            ) from exc
        _log_stage(
            db,
            account,
            scan,
            event="collection_stage_completed",
            stage="credentials",
            duration_ms=_elapsed_ms(auth_started),
        )

        collectors_started = time.monotonic()
        _log_stage(db, account, scan, event="collection_stage_started", stage="collectors")
        try:
            findings, collector_errors, failed_rule_keys = run_collectors(
                aws_session, regions, policies
            )
        except Exception as exc:
            info = classify_collection_error(exc)
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_failed",
                stage="collectors",
                duration_ms=_elapsed_ms(collectors_started),
                error=exc,
            )
            raise ProviderExecutionError(
                self.provider,
                exc,
                connection_failure=False,
                stage="collectors",
                category=info.category,
                retryable=info.retryable,
            ) from exc

        collector_errors = list(collector_errors)
        _log_stage(
            db,
            account,
            scan,
            event="collection_stage_partial" if collector_errors else "collection_stage_completed",
            stage="collectors",
            duration_ms=_elapsed_ms(collectors_started),
            warning_count=len(collector_errors),
        )
        active_rule_keys = [key for key in active_rule_keys if key not in failed_rule_keys]

        # Restore caller-visible ORM identity only after provider I/O has completed.
        # This preserves transaction-free network calls without leaking detached state
        # to scheduling or other code that continues using these same instances.
        db.add(account)
        db.add(scan)
        return CollectionExecutionResult(
            findings=findings,
            active_rule_keys=active_rule_keys,
            collector_errors=collector_errors,
            # The current AWS collectors do not expose the total evaluated resources.
            resources_analyzed=0,
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


class OciCollectionExecutor:
    provider = CloudProvider.OCI.value
    _CONNECTION_ERROR_TOKENS = (
        "credential",
        "credencial",
        "authentication",
        "autenticação",
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

    @staticmethod
    def _result_issue_count(result) -> int:
        return len(list(getattr(result, "warnings", []) or [])) + len(
            list(getattr(result, "errors", []) or [])
        )

    def _log_oci_result(
        self,
        db: Session,
        account: CloudAccount,
        scan: Scan,
        *,
        stage: str,
        result,
        started: float,
        resource_count: int | None = None,
    ) -> None:
        issues = self._result_issue_count(result)
        event = "collection_stage_completed"
        if getattr(result, "status", None) == "failed":
            event = "collection_stage_failed"
        elif issues:
            event = "collection_stage_partial"
        _log_stage(
            db,
            account,
            scan,
            event=event,
            stage=stage,
            duration_ms=_elapsed_ms(started),
            resource_count=resource_count,
            warning_count=issues,
        )

    def execute(
        self,
        db: Session,
        account: CloudAccount,
        scan: Scan,
    ) -> CollectionExecutionResult:
        self._configuration(db, account, scan=scan)
        _cache_run_id(db, scan)
        credentials_started = time.monotonic()
        _log_stage(db, account, scan, event="collection_stage_started", stage="credentials")
        try:
            snapshot = resolve_oci_signing_credentials(db, account.id)
        except OciConnectionError as exc:
            safe = RuntimeError(f"OCI credential failure: {exc.safe_message}")
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_failed",
                stage="credentials",
                duration_ms=_elapsed_ms(credentials_started),
                error=safe,
            )
            category = (
                "authentication" if exc.code != "local_configuration_invalid" else "configuration"
            )
            raise ProviderExecutionError(
                self.provider,
                safe,
                connection_failure=True,
                stage="credentials",
                category=category,
                retryable=False,
            ) from None
        except Exception as exc:
            safe = RuntimeError("OCI signing credentials could not be resolved")
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_failed",
                stage="credentials",
                duration_ms=_elapsed_ms(credentials_started),
                error=safe,
            )
            raise ProviderExecutionError(
                self.provider,
                safe,
                connection_failure=True,
                stage="credentials",
                category="configuration",
                retryable=False,
            ) from exc

        if snapshot.tenancy_ocid != account.native_account_id:
            safe = RuntimeError("OCI credential tenancy does not match the CloudAccount identity")
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_failed",
                stage="credentials",
                duration_ms=_elapsed_ms(credentials_started),
                error=safe,
            )
            raise ProviderExecutionError(
                self.provider,
                safe,
                connection_failure=True,
                stage="credentials",
                category="authentication",
                retryable=False,
            )
        _log_stage(
            db,
            account,
            scan,
            event="collection_stage_completed",
            stage="credentials",
            duration_ms=_elapsed_ms(credentials_started),
        )

        # No ORM object carrying credentials is persisted. Release the transaction before
        # read-only OCI network I/O while retaining only the in-memory, repr-safe snapshot.
        db.expunge(account)
        db.expunge(scan)
        db.commit()

        def cached_credentials(_db, _account_id):
            return snapshot

        current_stage = "discovery"
        stage_started = time.monotonic()
        try:
            _log_stage(db, account, scan, event="collection_stage_started", stage=current_stage)
            discovery_service = OciDiscoveryService(credential_resolver=cached_credentials)
            discovery = discovery_service.discover(snapshot)
            self._log_oci_result(
                db,
                account,
                scan,
                stage=current_stage,
                result=discovery,
                started=stage_started,
                resource_count=len(discovery.resources),
            )
            if discovery.status == "failed":
                connection_failure = self._fatal_connection_issue(discovery)
                message = self._safe_result_message(discovery, "OCI Discovery failed")
                if connection_failure:
                    message = f"OCI authentication failure: {message}"
                info = classify_collection_error(message)
                raise ProviderExecutionError(
                    self.provider,
                    RuntimeError(message),
                    connection_failure=connection_failure,
                    stage=current_stage,
                    category="authentication" if connection_failure else info.category,
                    retryable=info.retryable,
                )

            current_stage = "cloud_advisor"
            stage_started = time.monotonic()
            _log_stage(db, account, scan, event="collection_stage_started", stage=current_stage)
            advisor = OciCloudAdvisorService(credential_resolver=cached_credentials).collect(
                snapshot,
                discovery=discovery,
            )
            self._log_oci_result(
                db, account, scan, stage=current_stage, result=advisor, started=stage_started
            )

            current_stage = "usage"
            stage_started = time.monotonic()
            _log_stage(db, account, scan, event="collection_stage_started", stage=current_stage)
            usage = OciUsageService(credential_resolver=cached_credentials).collect_account(
                db,
                account.id,
                inventory=discovery,
            )
            self._log_oci_result(
                db, account, scan, stage=current_stage, result=usage, started=stage_started
            )

            current_stage = "monitoring"
            stage_started = time.monotonic()
            _log_stage(db, account, scan, event="collection_stage_started", stage=current_stage)
            monitoring_service = OciMonitoringService(credential_resolver=cached_credentials)
            monitoring = monitoring_service.collect_account(
                db,
                account.id,
                inventory=discovery,
            )
            self._log_oci_result(
                db, account, scan, stage=current_stage, result=monitoring, started=stage_started
            )

            for result, label, stage in (
                (advisor, "OCI Cloud Advisor", "cloud_advisor"),
                (usage, "OCI Usage API", "usage"),
                (monitoring, "OCI Monitoring", "monitoring"),
            ):
                if result.status == "failed" and self._fatal_connection_issue(result):
                    message = self._safe_result_message(result, f"{label} authentication failed")
                    raise ProviderExecutionError(
                        self.provider,
                        RuntimeError(f"OCI authentication failure: {message}"),
                        connection_failure=True,
                        stage=stage,
                        category="authentication",
                        retryable=False,
                    )

            current_stage = "correlation"
            stage_started = time.monotonic()
            _log_stage(db, account, scan, event="collection_stage_started", stage=current_stage)
            correlation = correlate_oci_datasets(discovery, advisor, usage, monitoring)
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_completed",
                stage=current_stage,
                duration_ms=_elapsed_ms(stage_started),
            )

            current_stage = "analyzers"
            stage_started = time.monotonic()
            _log_stage(db, account, scan, event="collection_stage_started", stage=current_stage)
            registry = OciAnalyzerRegistry()
            findings = OciAnalysisService(registry).analyze(correlation)
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_completed",
                stage=current_stage,
                duration_ms=_elapsed_ms(stage_started),
            )
        except ProviderExecutionError:
            raise
        except Exception as exc:
            info = classify_collection_error(exc)
            _log_stage(
                db,
                account,
                scan,
                event="collection_stage_failed",
                stage=current_stage,
                duration_ms=_elapsed_ms(stage_started),
                error=exc,
            )
            raise ProviderExecutionError(
                self.provider,
                RuntimeError("OCI collection pipeline failed"),
                connection_failure=False,
                stage=current_stage,
                category=info.category,
                retryable=info.retryable,
            ) from exc

        # Reattach only after OCI network I/O has completed successfully. Callers may
        # continue mutating the original account/scan instances (for example scheduling),
        # so leaving them detached would silently drop subsequent persisted changes.
        db.add(account)
        db.add(scan)
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
