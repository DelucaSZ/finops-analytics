# Reports Domain

## Architecture

Task 24.15A introduces the persistence foundation for Aven Reports without generating or delivering files.

```text
Report
  1:N
ReportExecution
  1:N
ReportArtifact
```

`Report` is the reusable business definition. `ReportExecution` is one asynchronous generation attempt and owns its lifecycle. `ReportArtifact` is an immutable logical reference to an externally stored artifact.

## Responsibilities

### Report

Stores the report name, product-aligned `report_type`, optional description, structured parameters, provider-neutral scope, creator attribution, and standard timestamps. It intentionally has no `current_status`/`is_generating` state because concurrent executions are valid.

The initial report types match domains already present in Aven: `COST`, `EXECUTIVE`, `INVENTORY`, `RESERVATIONS`, and `OPTIMIZATION`. The database column remains a string rather than a database enum so future product types can evolve without replacing a rigid database enum.

### ReportExecution

Represents one attempt to materialize a Report. A new execution starts as `QUEUED` and snapshots both `Report.parameters` and `Report.scope`. Later edits to the Report therefore cannot rewrite historical execution inputs.

The model also persists requester attribution, attempt number, safe execution metadata, start/finish timestamps, and sanitized diagnostic error fields.

### ReportArtifact

Represents metadata about an artifact produced by a successful execution. The database does not contain report binaries. It stores format, logical storage key, file name, content type, optional size/checksum, metadata, and creation timestamp.

## Lifecycle

The persistence service enforces the deliberately small lifecycle:

```text
QUEUED
  |
  v
RUNNING
  |----> SUCCESS
  `----> FAILED
```

Terminal executions cannot return to `RUNNING`. `started_at` is set when processing starts; `finished_at` is set for `SUCCESS` or `FAILED`. Artifacts may only be registered for a successful execution.

This model is naturally safe for multiple simultaneous executions because execution state never lives on `Report`.

## Parameters

`Report.parameters` is structured JSON. `ReportExecution.parameters_snapshot` is a deep copy of the parameters that applied when the execution was requested.

The persistence service rejects metadata keys that look like credentials or secrets (`access_key`, `secret`, `token`, `password`, `private_key`, credentials, authorization, or signed URLs). Parameters are backend-persisted and are not dependent on frontend state.

## Scope

`Report.scope` and `ReportExecution.scope_snapshot` are provider-neutral JSON documents. They can represent provider/account/region/business dimensions without making an AWS account or OCI compartment mandatory in the core domain.

Example:

```json
{
  "providers": ["AWS", "OCI"],
  "cloud_account_ids": [12, 25],
  "regions": ["us-east-1", "sa-saopaulo-1"]
}
```

No new organization/workspace tenancy concept is introduced by this task. The current backend has global users and cloud-account boundaries; Reports preserve user creator/requester attribution and leave authorization enforcement to the future Reports API using the application's existing security model.

## Artifact Storage

`ReportArtifact.storage_key` is the source of truth for object location. Public/signed HTTP URLs are explicitly rejected as storage keys. A future storage service may resolve the logical key through Local Storage, AWS S3, OCI Object Storage, or another provider without changing the Reports domain.

Initial modeled formats are `PDF`, `CSV`, `XLSX`, and `JSON`. Task 24.15A adds no PDF/Excel libraries, renderer, storage implementation, dummy file, or download endpoint.

## Referential Integrity and Indexes

Foreign keys enforce the graph:

- `ReportExecution.report_id -> Report.id`;
- `ReportArtifact.report_execution_id -> ReportExecution.id`;
- `created_by` / `requested_by -> User.id` with `SET NULL` so historical business records survive user removal.

Report-owned execution/artifact records cascade when the parent report graph is deliberately deleted. Indexes cover the expected future API access patterns by creator/type/creation time, execution status/report/requester, and artifact execution/format.

## Multi-cloud

The domain does not contain `aws_report`, mandatory `aws_account_id`, mandatory AWS region, OCI-specific compartment columns, or provider-specific storage URLs. Provider-specific identifiers, when needed, belong inside the structured scope under the same cloud-account abstraction used by the rest of Aven.

## Security

The persistence layer:

- rejects obvious secret-bearing keys from parameters, scope, execution metadata, and artifact metadata;
- stores no cloud credentials;
- stores no permanent public or signed artifact URL;
- collapses multiline error payloads, redacts common credential assignments, and caps persisted error messages;
- does not persist stack traces as an error-storage contract.

The future API must apply the application's existing authentication/RBAC rules before calling these persistence methods.

## Collections Independence

`CollectionRun` is unchanged. A collection observes/analyzes cloud state; a ReportExecution later materializes data already available in Aven. Reports may consume collection-derived data in a future generation engine, but there is no mandatory lifecycle or foreign-key dependency between the two domains.

## Future Tasks

- **24.15B — Report Generation Engine:** asynchronous generation/renderer orchestration using the execution lifecycle and snapshots defined here.
- **24.15C — Reports API & Artifact Delivery:** authenticated HTTP contracts, execution requests, history, storage resolution, and artifact delivery.
- **24.15 — Aven Reports Experience:** Aven UI for report definitions, generation/history/status and downloads.

Scheduling (`ReportSchedule`) and templates (`ReportTemplate`) are intentionally not introduced here. The 1:N execution model leaves both extensions possible without redesigning execution persistence.
