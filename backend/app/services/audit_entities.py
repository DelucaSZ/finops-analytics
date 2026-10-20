from __future__ import annotations

from app.core.cloud import CloudProvider
from app.models.account import CloudAccount
from app.services.audit import audit_snapshot
from app.services.cloud_accounts import require_aws_configuration, require_oci_configuration


def cloud_account_audit_snapshot(account: CloudAccount) -> dict:
    configuration: dict = {}
    if account.provider == CloudProvider.AWS.value:
        aws = require_aws_configuration(account)
        configuration = {
            "role_arn": aws.role_arn,
            "regions": list(aws.regions or []),
            "is_management_account": aws.is_management_account,
        }
    elif account.provider == CloudProvider.OCI.value:
        oci = require_oci_configuration(account)
        configuration = {
            "user_ocid": oci.user_ocid,
            "fingerprint": oci.fingerprint,
            "region": oci.region,
            "scope_regions": list(oci.scope_regions or []),
            "compartment_ocids": list(oci.compartment_ocids or []),
            "include_root_compartment": oci.include_root_compartment,
            "include_subcompartments": oci.include_subcompartments,
            "credentials_configured": oci.credentials_configured,
            "credential_revision": oci.credential_revision,
        }
    return audit_snapshot(
        {
            "provider": account.provider,
            "native_account_id": account.native_account_id,
            "name": account.name,
            "enabled": account.enabled,
            "schedule_enabled": account.schedule_enabled,
            "scan_interval_hours": account.scan_interval_hours,
            "configuration": configuration,
        }
    )


def cloud_account_audit_label(account: CloudAccount) -> str:
    return f"{account.provider.upper()} · {account.name} · {account.native_account_id}"


def cloud_account_update_action(before: dict, after: dict) -> str | None:
    if before == after:
        return None
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    if changed == {"enabled"}:
        return "account.enable" if after.get("enabled") else "account.disable"
    if changed and changed <= {"schedule_enabled", "scan_interval_hours"}:
        return "account.schedule_update"
    return "account.update"
