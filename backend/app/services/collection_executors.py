from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider, normalize_provider
from app.models.account import AwsAccount, CloudAccount
from app.models.scan import Scan
from app.services.aws_auth import assume_account_session, get_caller_identity
from app.services.collector_types import CollectedFinding
from app.services.collectors import run_collectors
from app.services.policies import list_effective_policies
from app.services.provider_capabilities import ProviderOperation, require_provider_operation


class CollectionPreconditionError(ValueError):
    """Collection cannot start because an administrative precondition is not satisfied."""


class CollectionExecutorUnavailable(CollectionPreconditionError):
    """No operational collection executor is registered for the provider."""


class ProviderExecutionError(RuntimeError):
    """A provider call failed after collection preconditions were satisfied."""

    def __init__(self, provider: str, cause: Exception):
        self.provider = provider
        self.cause = cause
        super().__init__(str(cause))


@dataclass(frozen=True)
class CollectionPreparation:
    legacy_scan_account_id: int
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


COLLECTION_EXECUTORS = CollectionExecutorRegistry((AwsCollectionExecutor(),))


def get_collection_executor(provider: str) -> CollectionExecutor:
    return COLLECTION_EXECUTORS.get(provider)


def has_collection_executor(provider: str) -> bool:
    return COLLECTION_EXECUTORS.has(provider)
