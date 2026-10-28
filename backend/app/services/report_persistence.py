"""Persistence operations and lifecycle invariants for the Reports domain."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.report import (
    Report,
    ReportArtifact,
    ReportArtifactFormat,
    ReportExecution,
    ReportExecutionStatus,
    ReportType,
)

_SENSITIVE_KEY_PARTS = (
    "access_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "signed_url",
    "token",
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(access[_ -]?key|authorization|credential|password|private[_ -]?key|secret|token)\b"
    r"\s*[:=]\s*\S+"
)
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ReportExecutionStatus.QUEUED.value: {ReportExecutionStatus.RUNNING.value},
    ReportExecutionStatus.RUNNING.value: {
        ReportExecutionStatus.SUCCESS.value,
        ReportExecutionStatus.FAILED.value,
    },
    ReportExecutionStatus.SUCCESS.value: set(),
    ReportExecutionStatus.FAILED.value: set(),
}


def _enum_value(value: str | Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _safe_mapping(value: dict | None, *, field_name: str) -> dict:
    candidate = deepcopy(value or {})

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                normalized = str(key).lower().replace("-", "_").replace(" ", "_")
                if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                    raise ValueError(f"{field_name} contains a sensitive key at {path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")

    visit(candidate, field_name)
    return candidate


def _safe_error_message(message: str | None) -> str | None:
    if not message:
        return None
    # Error persistence is diagnostic, not a log sink: collapse multiline trace output,
    # redact obvious credential assignments, and cap the stored message.
    sanitized = " ".join(message.splitlines())
    sanitized = _CREDENTIAL_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", sanitized)
    return sanitized[:2000]


class ReportPersistenceService:
    """Transaction-neutral persistence façade for Reports.

    Methods flush when an identifier is required, but never commit. The caller owns
    the transaction boundary, matching the existing backend service convention.
    """

    def create_report(
        self,
        db: Session,
        *,
        name: str,
        report_type: ReportType | str,
        description: str | None = None,
        parameters: dict | None = None,
        scope: dict | None = None,
        created_by: str | None = None,
    ) -> Report:
        type_value = _enum_value(report_type)
        if type_value not in {item.value for item in ReportType}:
            raise ValueError(f"Unsupported report type: {type_value}")
        if not name.strip():
            raise ValueError("Report name is required")
        report = Report(
            name=name.strip(),
            report_type=type_value,
            description=description,
            parameters=_safe_mapping(parameters, field_name="parameters"),
            scope=_safe_mapping(scope, field_name="scope"),
            created_by=created_by,
        )
        db.add(report)
        db.flush()
        return report

    @staticmethod
    def get_report(db: Session, report_id: str) -> Report | None:
        return db.get(Report, report_id)

    @staticmethod
    def list_reports(
        db: Session,
        *,
        created_by: str | None = None,
        report_type: ReportType | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Report]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        statement = select(Report)
        if created_by is not None:
            statement = statement.where(Report.created_by == created_by)
        if report_type is not None:
            statement = statement.where(Report.report_type == _enum_value(report_type))
        statement = statement.order_by(Report.created_at.desc(), Report.id.desc())
        return list(db.scalars(statement.offset(offset).limit(limit)).all())

    def create_execution(
        self,
        db: Session,
        *,
        report: Report,
        requested_by: str | None = None,
        attempt: int = 1,
        execution_metadata: dict | None = None,
    ) -> ReportExecution:
        if not report.id:
            raise ValueError("Report must be persisted before execution")
        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        execution = ReportExecution(
            report_id=report.id,
            status=ReportExecutionStatus.QUEUED.value,
            parameters_snapshot=deepcopy(report.parameters or {}),
            scope_snapshot=deepcopy(report.scope or {}),
            requested_by=requested_by,
            attempt=attempt,
            execution_metadata=_safe_mapping(
                execution_metadata, field_name="execution_metadata"
            ),
        )
        db.add(execution)
        db.flush()
        return execution

    @staticmethod
    def get_execution(db: Session, execution_id: str) -> ReportExecution | None:
        return db.get(ReportExecution, execution_id)

    def update_execution_status(
        self,
        db: Session,
        *,
        execution: ReportExecution,
        status: ReportExecutionStatus | str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ReportExecution:
        target = _enum_value(status)
        if target not in {item.value for item in ReportExecutionStatus}:
            raise ValueError(f"Unsupported execution status: {target}")
        current = execution.status
        if target not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid report execution transition: {current} -> {target}")

        now = utcnow()
        execution.status = target
        if target == ReportExecutionStatus.RUNNING.value:
            execution.started_at = execution.started_at or now
            execution.finished_at = None
            execution.error_code = None
            execution.error_message = None
        elif target == ReportExecutionStatus.SUCCESS.value:
            execution.finished_at = now
            execution.error_code = None
            execution.error_message = None
        elif target == ReportExecutionStatus.FAILED.value:
            execution.finished_at = now
            execution.error_code = error_code[:64] if error_code else None
            execution.error_message = _safe_error_message(error_message)
        db.flush()
        return execution

    def create_artifact(
        self,
        db: Session,
        *,
        execution: ReportExecution,
        format: ReportArtifactFormat | str,
        storage_key: str,
        file_name: str,
        content_type: str,
        size_bytes: int | None = None,
        checksum: str | None = None,
        metadata: dict | None = None,
    ) -> ReportArtifact:
        if execution.status != ReportExecutionStatus.SUCCESS.value:
            raise ValueError("Artifacts can only be registered for successful executions")
        format_value = _enum_value(format)
        if format_value not in {item.value for item in ReportArtifactFormat}:
            raise ValueError(f"Unsupported artifact format: {format_value}")
        if storage_key.lower().startswith(("http://", "https://")):
            raise ValueError("storage_key must be a logical storage reference, not a public URL")
        if not storage_key.strip():
            raise ValueError("storage_key is required")
        if size_bytes is not None and size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        artifact = ReportArtifact(
            report_execution_id=execution.id,
            format=format_value,
            storage_key=storage_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
            artifact_metadata=_safe_mapping(metadata, field_name="metadata"),
        )
        db.add(artifact)
        db.flush()
        return artifact

    @staticmethod
    def list_artifacts(db: Session, *, execution_id: str) -> list[ReportArtifact]:
        statement = (
            select(ReportArtifact)
            .where(ReportArtifact.report_execution_id == execution_id)
            .order_by(ReportArtifact.created_at.asc(), ReportArtifact.id.asc())
        )
        return list(db.scalars(statement).all())
