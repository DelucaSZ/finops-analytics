# AWS onboarding

## Authentication model

NuvemIQ uses two role layers:

1. `NuvemIQCentralRole` is attached to the EC2 instance through an instance
   profile.
2. `NuvemIQReadOnly` exists in every analyzed account and trusts only the
   central role, guarded by a unique External ID.

No IAM user or long-lived Access Key is required.

## 1. Hosting account

Deploy `infrastructure/cloudformation/nuvemiq-central-role.yaml` in the account
that hosts the EC2 instance.

Parameters:

- `RoleName`: normally `NuvemIQCentralRole`;
- `TargetRoleName`: normally `NuvemIQReadOnly`;
- `EnableBedrock`: `true` only when AI explanations will be used.

Attach the stack's `InstanceProfileName` output to the EC2 instance. Keep the
`CentralRoleArn` output for the next step.

## 2. Target accounts

For each AWS account:

1. Generate or copy the External ID from the NuvemIQ account form.
2. Deploy `infrastructure/cloudformation/nuvemiq-readonly-role.yaml`.
3. Supply the central role ARN and that account's External ID.
4. Copy the target stack's `RoleArn` output to NuvemIQ.
5. Select the regions that should be inventoried.
6. Save and run **Test connection**.

The Account ID entered in NuvemIQ must match the account contained in the Role
ARN. The API rejects mismatched values.

## 3. Cost data

Cost Explorer must be enabled before the cost-growth detector can return data.
For organization-wide consolidated analysis, register the management/payer
account and mark it accordingly in NuvemIQ.

Some billing APIs can require explicit console settings in addition to IAM
permissions. A failure in one collector is recorded as a warning and does not
discard results from the other collectors.

## 4. Least privilege hardening

The MVP target template starts with AWS managed read-only policies plus explicit
Cost Explorer permissions. After a validation period, use CloudTrail and IAM
Access Analyzer to create a narrower customer-managed policy based on the APIs
actually used in your environment.
