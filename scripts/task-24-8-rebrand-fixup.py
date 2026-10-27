#!/usr/bin/env python3
"""One-shot Task 24.8 source rewrite for already-classified public DeepOps/NuvemIQ copy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEEPOPS_PUBLIC_FILES = [
    "frontend/app/settings/accounts/page.tsx",
    "frontend/app/settings/https/page.tsx",
    "frontend/app/settings/policies/page.tsx",
    "frontend/app/settings/pricing/oci/page.tsx",
    "frontend/app/settings/usage-costs/page.tsx",
    "backend/app/__init__.py",
    "backend/app/commands/__init__.py",
    "backend/app/commands/rds_inventory.py",
    "backend/app/models/billing_profile.py",
    "backend/app/models/cloudwatch_pricing.py",
    "backend/app/schemas/billing.py",
    "backend/app/services/ai.py",
    "backend/app/services/aws_billing.py",
    "backend/app/services/aws_cost_explorer.py",
    "backend/app/services/cloudwatch_cost_engine.py",
    "backend/app/services/collection_comparison.py",
    "backend/app/services/mfa.py",
    "backend/app/services/oci_pricing.py",
    "backend/app/services/oci_usage.py",
    "backend/app/services/opportunity_evidence.py",
    "backend/app/services/rds_reservation_opportunities.py",
    "backend/app/services/tls_manager.py",
]

NUVEMIQ_PUBLIC_FILES = [
    "backend/app/worker.py",
    "backend/app/worker_runtime.py",
]


def rewrite(relative: str, replacements: list[tuple[str, str]]) -> int:
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    updated = source
    changes = 0
    for old, new in replacements:
        count = updated.count(old)
        if count:
            updated = updated.replace(old, new)
            changes += count
    if updated != source:
        path.write_text(updated, encoding="utf-8")
    print(f"{relative}: {changes} replacement(s)")
    return changes


def main() -> None:
    total = 0
    # The IAM role shown in Settings is an example value, not an infrastructure contract.
    total += rewrite(
        "frontend/app/settings/accounts/page.tsx",
        [("DeepOpsReadOnly", "FinOpsReadOnly")],
    )

    for relative in DEEPOPS_PUBLIC_FILES:
        total += rewrite(relative, [("DeepOps", "Aven")])

    total += rewrite(
        "frontend/app/settings/https/page.tsx",
        [("deepops.exemplo.com", "aven.exemplo.com")],
    )

    for relative in NUVEMIQ_PUBLIC_FILES:
        total += rewrite(relative, [("NuvemIQ worker started", "Aven worker started")])

    print(f"Task 24.8 public-brand replacements: {total}")


if __name__ == "__main__":
    main()
