"""Persisted single-unit manual queue consumed only by the existing worker.

An HTTP request inserts a row and returns 202. Network download, parsing and
publication happen only here, through the Task 28.4 synchronizer.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal
from app.models.aws_pricing import AwsPricingSyncRequest
from app.services.aws_pricing_sync import AwsPricingSynchronizer

logger = logging.getLogger(__name__)


class AwsPricingManualQueue:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
        synchronizer: AwsPricingSynchronizer | None = None,
    ) -> None:
        self.sessions = session_factory
        self.synchronizer = synchronizer or AwsPricingSynchronizer(session_factory=session_factory)

    def run_next(self) -> dict | None:
        # Opt-in applies equally to automatic and manual publication.
        if os.environ.get("AVEN_AWS_PRICING_IMPORT_ENABLED") != "1":
            return None
        with self.sessions.begin() as db:
            # A worker that terminated mid-job can leave a request running.
            # Long-running downloads are protected by the 28.4 advisory lock.
            cutoff = datetime.now(UTC) - timedelta(hours=12)
            abandoned = db.scalars(
                select(AwsPricingSyncRequest)
                .where(
                    AwsPricingSyncRequest.status == "running",
                    AwsPricingSyncRequest.started_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
            for old in abandoned:
                old.status = "queued"
                old.started_at = None
                old.error_code = "worker_interrupted"
            row = db.scalar(
                select(AwsPricingSyncRequest)
                .where(AwsPricingSyncRequest.status == "queued")
                .order_by(AwsPricingSyncRequest.requested_at, AwsPricingSyncRequest.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            row.status = "running"
            row.started_at = datetime.now(UTC)
            request = {
                "id": row.id,
                "service_code": row.service_code,
                "region_code": row.region_code,
                "dry_run": row.dry_run,
                "force": row.force,
            }
        try:
            result = self.synchronizer.run_unit(
                request["service_code"],
                request["region_code"],
                trigger="manual",
                dry_run=request["dry_run"],
                force=request["force"],
            )
            with self.sessions.begin() as db:
                row = db.get(AwsPricingSyncRequest, request["id"])
                if row is None:
                    raise RuntimeError("AWS sync request disappeared")
                row.result = result
                if result.get("status") == "busy":
                    # Another process owns the unit lock. Defer safely.
                    row.status = "queued"
                    row.started_at = None
                    row.error_code = "sync_busy"
                else:
                    row.status = "failed" if result.get("status") == "failed" else "completed"
                    row.error_code = result.get("error_code")
                    row.finished_at = datetime.now(UTC)
            return result
        except Exception as exc:
            logger.exception("event=aws_manual_pricing_sync_failed request_id=%s", request["id"])
            with self.sessions.begin() as db:
                row = db.get(AwsPricingSyncRequest, request["id"])
                if row:
                    row.status = "failed"
                    row.finished_at = datetime.now(UTC)
                    row.error_code = type(exc).__name__[:100]
            return {"status": "failed", "error_code": type(exc).__name__[:100]}
