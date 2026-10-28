from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.migrations import migration_config
from app.models.report import (
    ReportArtifact,
    ReportArtifactFormat,
    ReportExecution,
    ReportExecutionStatus,
    ReportType,
)
from app.models.user import User
from app.services.report_persistence import ReportPersistenceService


def _session() -> tuple[Session, object]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return Session(engine), engine


def _user(db: Session, *, name: str = "Reports User") -> User:
    user = User(
        name=name,
        email=f"{name.lower().replace(' ', '.')}@example.test",
        password_hash="not-used",
        role="operator",
    )
    db.add(user)
    db.flush()
    return user


def test_report_persists_definition_scope_parameters_and_ownership():
    db, engine = _session()
    try:
        actor = _user(db)
        service = ReportPersistenceService()
        report = service.create_report(
            db,
            name="Monthly Cost Report",
            report_type=ReportType.COST,
            description="Monthly cost posture",
            parameters={"date_from": "2026-09-01", "currency": "USD"},
            scope={"providers": ["AWS", "OCI"], "cloud_account_ids": [1, 2]},
            created_by=actor.id,
        )
        db.commit()

        loaded = service.get_report(db, report.id)
        assert loaded is not None
        assert loaded.report_type == ReportType.COST.value
        assert loaded.parameters["currency"] == "USD"
        assert loaded.scope["providers"] == ["AWS", "OCI"]
        assert loaded.created_by == actor.id
        assert service.list_reports(db, created_by=actor.id) == [loaded]
    finally:
        db.close()
        engine.dispose()


def test_execution_starts_queued_preserves_snapshots_and_enforces_lifecycle():
    db, engine = _session()
    try:
        actor = _user(db)
        service = ReportPersistenceService()
        report = service.create_report(
            db,
            name="Inventory Report",
            report_type=ReportType.INVENTORY,
            parameters={"providers": ["AWS"]},
            scope={"cloud_account_ids": [10]},
            created_by=actor.id,
        )
        execution = service.create_execution(db, report=report, requested_by=actor.id)
        assert execution.status == ReportExecutionStatus.QUEUED.value
        assert execution.started_at is None
        assert execution.finished_at is None

        report.parameters = {"providers": ["OCI"]}
        report.scope = {"cloud_account_ids": [20]}
        assert execution.parameters_snapshot == {"providers": ["AWS"]}
        assert execution.scope_snapshot == {"cloud_account_ids": [10]}

        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.RUNNING
        )
        assert execution.started_at is not None
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.SUCCESS
        )
        assert execution.finished_at is not None

        try:
            service.update_execution_status(
                db, execution=execution, status=ReportExecutionStatus.RUNNING
            )
        except ValueError as exc:
            assert "Invalid report execution transition" in str(exc)
        else:
            raise AssertionError("terminal execution accepted an invalid transition")
    finally:
        db.close()
        engine.dispose()


def test_failed_execution_persists_safe_diagnostic_error():
    db, engine = _session()
    try:
        actor = _user(db)
        service = ReportPersistenceService()
        report = service.create_report(
            db,
            name="Optimization Report",
            report_type=ReportType.OPTIMIZATION,
            created_by=actor.id,
        )
        execution = service.create_execution(db, report=report, requested_by=actor.id)
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.RUNNING
        )
        service.update_execution_status(
            db,
            execution=execution,
            status=ReportExecutionStatus.FAILED,
            error_code="RENDER_FAILED",
            error_message="renderer failed\ntoken=super-secret-value\ntrace line",
        )

        assert execution.error_code == "RENDER_FAILED"
        assert "super-secret-value" not in execution.error_message
        assert "[REDACTED]" in execution.error_message
        assert "\n" not in execution.error_message
        assert execution.finished_at is not None
    finally:
        db.close()
        engine.dispose()


def test_successful_execution_supports_multiple_storage_agnostic_artifacts():
    db, engine = _session()
    try:
        actor = _user(db)
        service = ReportPersistenceService()
        report = service.create_report(
            db,
            name="Executive FinOps Report",
            report_type=ReportType.EXECUTIVE,
            scope={"providers": ["AWS", "OCI"]},
            created_by=actor.id,
        )
        execution = service.create_execution(db, report=report, requested_by=actor.id)
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.RUNNING
        )
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.SUCCESS
        )

        pdf = service.create_artifact(
            db,
            execution=execution,
            format=ReportArtifactFormat.PDF,
            storage_key=f"reports/{execution.id}/executive.pdf",
            file_name="executive.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="sha256:abc",
            metadata={"renderer_version": "future-engine"},
        )
        csv = service.create_artifact(
            db,
            execution=execution,
            format=ReportArtifactFormat.CSV,
            storage_key=f"reports/{execution.id}/executive.csv",
            file_name="executive.csv",
            content_type="text/csv",
            size_bytes=512,
        )
        db.commit()

        artifacts = service.list_artifacts(db, execution_id=execution.id)
        assert [item.id for item in artifacts] == [pdf.id, csv.id]
        assert pdf.artifact_metadata == {"renderer_version": "future-engine"}
        assert pdf.report_execution_id == execution.id
    finally:
        db.close()
        engine.dispose()


def test_sensitive_metadata_and_public_storage_urls_are_rejected():
    db, engine = _session()
    try:
        actor = _user(db)
        service = ReportPersistenceService()
        try:
            service.create_report(
                db,
                name="Unsafe",
                report_type=ReportType.COST,
                parameters={"access_key": "AKIA..."},
                created_by=actor.id,
            )
        except ValueError as exc:
            assert "sensitive key" in str(exc)
        else:
            raise AssertionError("sensitive report parameter was accepted")

        report = service.create_report(
            db, name="Safe", report_type=ReportType.COST, created_by=actor.id
        )
        execution = service.create_execution(db, report=report, requested_by=actor.id)
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.RUNNING
        )
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.SUCCESS
        )
        try:
            service.create_artifact(
                db,
                execution=execution,
                format=ReportArtifactFormat.JSON,
                storage_key="https://example.test/signed-report",
                file_name="report.json",
                content_type="application/json",
            )
        except ValueError as exc:
            assert "logical storage reference" in str(exc)
        else:
            raise AssertionError("public URL was accepted as storage source of truth")
    finally:
        db.close()
        engine.dispose()


def test_foreign_keys_and_cascade_keep_report_graph_integral():
    db, engine = _session()
    try:
        actor = _user(db)
        service = ReportPersistenceService()
        report = service.create_report(
            db, name="Graph", report_type=ReportType.RESERVATIONS, created_by=actor.id
        )
        execution = service.create_execution(db, report=report, requested_by=actor.id)
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.RUNNING
        )
        service.update_execution_status(
            db, execution=execution, status=ReportExecutionStatus.SUCCESS
        )
        artifact = service.create_artifact(
            db,
            execution=execution,
            format=ReportArtifactFormat.XLSX,
            storage_key=f"reports/{execution.id}/coverage.xlsx",
            file_name="coverage.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.commit()
        execution_id, artifact_id = execution.id, artifact.id

        db.delete(report)
        db.commit()
        assert db.get(ReportExecution, execution_id) is None
        assert db.get(ReportArtifact, artifact_id) is None
    finally:
        db.close()
        engine.dispose()


def test_reports_migration_is_current_head():
    from alembic.script import ScriptDirectory

    script_directory = ScriptDirectory.from_config(migration_config())
    assert script_directory.get_current_head() == "0038_reports_domain"
