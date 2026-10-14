# AWS onboarding

## Authentication model

DeepOps uses two role layers:

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

1. Generate or copy the External ID from the DeepOps account form.
2. Deploy `infrastructure/cloudformation/nuvemiq-readonly-role.yaml`.
3. Supply the central role ARN and that account's External ID.
4. Copy the target stack's `RoleArn` output to DeepOps.
5. Select the regions that should be inventoried.
6. Save and run **Test connection**.

The Account ID entered in DeepOps must match the account contained in the Role
ARN. The API rejects mismatched values.

## 3. Cost data

Cost Explorer must be enabled before Billing or the cost-growth detector can
return data. Cost Explorer is queried with the same assumed role already used
for AWS collection; Billing does not introduce long-lived credentials.

For Task 23.14, the only IAM action required by the new Billing backend is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ce:GetCostAndUsage",
      "Resource": "*"
    }
  ]
}
```

The repository's `NuvemIQReadOnly` CloudFormation template already grants this
action. It also contains other Cost Explorer/Pricing actions used by existing or
separate DeepOps capabilities; those broader permissions are not required by
the Task 23.14 Billing query itself.

AWS Cost Explorer is exposed through the `us-east-1` billing endpoint even when
the analyzed resources live in other regions. DeepOps therefore creates the
Cost Explorer client in `us-east-1` while continuing to assume the target
account role using the existing authentication path.

### Management/payer, member and standalone accounts

AWS gives a management account visibility over its organization, while a member
account normally has only its own cost data. Member Cost Explorer access can
also be disabled centrally in Cost Explorer preferences, in which case IAM
permission alone is not sufficient.

The current DeepOps data model records whether an AWS account is a management
account, but it does not persist a payer/member relationship between registered
accounts. To avoid inventing or mixing billing scopes, Task 23.14 treats every
registered role as an independent billing scope:

- member/standalone account: assume its configured role and query its own Cost
  Explorer data;
- management account: assume its configured role and constrain the Cost
  Explorer query to that management account's own `LINKED_ACCOUNT` ID;
- multi-account DeepOps requests aggregate only complete results from the
  explicitly requested registered accounts; if one account fails, the aggregate
  request fails instead of returning a silently partial total.

This strategy intentionally does not use a management account to query arbitrary
member IDs until DeepOps has an explicit, trustworthy payer/member relationship.
The Billing API accepts DeepOps internal account IDs, resolves the corresponding
AWS Account IDs server-side, and never accepts a raw linked-account selector from
the client.

## 4. Least privilege hardening

The MVP target template starts with AWS managed read-only policies plus explicit
Cost Explorer permissions. After a validation period, use CloudTrail and IAM
Access Analyzer to create a narrower customer-managed policy based on the APIs
actually used in your environment.
