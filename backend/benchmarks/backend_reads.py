"""Synthetic read-only HTTP benchmark; never connects to application DATABASE_URL."""

import argparse
import hashlib
import json
import os
import statistics
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.api.routes import collections, dashboard, opportunities
from app.core.security import require_user
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation


def seed(engine, accounts, per_account):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    evidence = {"volume_size_gb": 100, "padding": "x" * 2048}
    with engine.begin() as conn:
        for a in range(accounts):
            native = f"{a:012d}"
            provider = ["aws", "oci", "azure", "gcp"][a % 4]
            if provider == "aws":
                conn.execute(
                    insert(AwsAccount),
                    dict(
                        name=f"Account {a}",
                        aws_account_id=native,
                        role_arn="synthetic",
                        external_id="synthetic",
                    ),
                )
            runs = [
                dict(
                    id=f"run-{a}-{r}",
                    provider=provider,
                    account_id=native,
                    status="SUCCESS",
                    started_at=start + timedelta(days=r),
                    finished_at=start + timedelta(days=r, minutes=1),
                    analyzer_version="v1",
                    created_at=start,
                    updated_at=start,
                )
                for r in range(100)
            ]
            conn.execute(insert(CollectionRun), runs)
            findings = [
                dict(
                    id=f"opp-{a}-{i:06d}",
                    fingerprint=hashlib.sha256(f"{a}-{i}".encode()).hexdigest(),
                    provider=provider,
                    account_id=native,
                    rule_key="ebs_unattached",
                    service="EBS",
                    resource_id=f"vol-{i}",
                    title=f"Volume {i}",
                    description="Synthetic unattached volume",
                    evidence=evidence,
                    severity=["high", "medium", "low"][i % 3],
                    status=["open", "treated", "rejected"][i % 3],
                    first_seen_at=start,
                    last_seen_at=start + timedelta(days=99),
                    current_monthly_cost=10,
                    estimated_monthly_savings=10,
                )
                for i in range(per_account)
            ]
            conn.execute(insert(Finding), findings)
            for r in range(90, 100):
                obs = [
                    dict(
                        id=f"obs-{a}-{r}-{i}",
                        opportunity_id=f"opp-{a}-{i:06d}",
                        collection_run_id=f"run-{a}-{r}",
                        observed_at=start + timedelta(days=r),
                        severity="high",
                        confidence="high",
                        current_monthly_cost=10,
                        estimated_monthly_savings=11 if r == 99 and i % 5 == 0 else 10,
                        evidence=evidence,
                    )
                    for i in range(per_account)
                    if not (r == 98 and i % 10 == 8 or r == 99 and i % 10 == 9)
                ]
                conn.execute(insert(OpportunityObservation), obs)
        conn.exec_driver_sql("ANALYZE")


@contextmanager
def benchmark_engine(postgres=False):
    """Create only disposable synthetic data, never use application DATABASE_URL."""
    if postgres:
        url = os.environ["TEST_POSTGRES_URL"]
        schema = "benchmark_" + uuid.uuid4().hex
        control = create_engine(url)
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        try:
            yield engine
        finally:
            engine.dispose()
            with control.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            control.dispose()
    else:
        with tempfile.TemporaryDirectory(prefix="deepops-benchmark-") as directory:
            engine = create_engine(
                f"sqlite:///{directory}/synthetic.db", connect_args={"check_same_thread": False}
            )
            try:
                yield engine
            finally:
                engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", type=int, default=20)
    parser.add_argument("--per-account", type=int, default=500)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--postgres", action="store_true", help="Use TEST_POSTGRES_URL in a new isolated schema"
    )
    parser.add_argument(
        "--explain", action="store_true", help="Read-only query plans, outside timing"
    )
    args = parser.parse_args()
    if args.accounts < 1 or args.per_account < 10 or args.repeat < 1:
        parser.error("accounts/repeat must be positive and per-account must be >= 10")
    with benchmark_engine(args.postgres) as engine:
        Base.metadata.create_all(engine)
        seed(engine, args.accounts, args.per_account)
        app = FastAPI()
        for router in (collections.router, dashboard.router, opportunities.router):
            app.include_router(router, prefix="/api/v1")

        def session():
            with Session(engine) as db:
                yield db

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[require_user] = lambda: None
        metrics = {"queries": 0, "orm_loaded": 0}

        statements = []

        def query(_conn, _cursor, statement, parameters, _context, _many):
            metrics["queries"] += 1
            statements.append((statement, parameters))

        def loaded(*_):
            metrics["orm_loaded"] += 1

        event.listen(engine, "before_cursor_execute", query)
        event.listen(Session, "loaded_as_persistent", loaded)
        paths = [
            "/dashboard/summary",
            "/dashboard/collection-health",
            "/opportunities?page=1&page_size=50",
            "/opportunities?current=true&status=open&page_size=50",
            "/opportunities?provider=aws&account_id=000000000000&status=open&severity=high&page_size=50",
            "/opportunities/opp-0-000000",
            "/opportunities/opp-0-000000/history?page_size=50",
            "/collections?page=1&page_size=50",
            "/collections/run-0-99",
            "/collections/run-0-99/compare?baseline_id=run-0-98&category=NEW&page_size=50",
            "/collections/run-0-99/compare?baseline_id=run-0-98&category=CHANGED&page_size=50",
        ]
        results = []
        try:
            with TestClient(app) as http:
                for path in paths:
                    times = []
                    for _ in range(args.repeat):
                        metrics.update(queries=0, orm_loaded=0)
                        statements.clear()
                        before = time.perf_counter()
                        response = http.get("/api/v1" + path)
                        times.append((time.perf_counter() - before) * 1000)
                        assert response.status_code == 200, (path, response.text)
                    results.append(
                        dict(
                            endpoint=path,
                            median_ms=round(statistics.median(times), 2),
                            **metrics,
                            payload_bytes=len(response.content),
                            response_sha256=hashlib.sha256(response.content).hexdigest(),
                        )
                    )
                    if args.explain:
                        captured = list(statements)
                        prefix = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
                            if engine.dialect.name == "postgresql"
                            else "EXPLAIN QUERY PLAN "
                        )
                        with engine.connect() as connection:
                            results[-1]["plans"] = [
                                [
                                    list(row)
                                    for row in connection.exec_driver_sql(prefix + sql, params)
                                ]
                                for sql, params in captured
                            ]
        finally:
            event.remove(engine, "before_cursor_execute", query)
            event.remove(Session, "loaded_as_persistent", loaded)
        print(
            json.dumps(
                dict(
                    database=engine.dialect.name,
                    measurement="Synthetic HTTP TestClient; auth excluded; no cloud calls",
                    accounts=args.accounts,
                    opportunities=args.accounts * args.per_account,
                    runs=args.accounts * 100,
                    observations=args.accounts
                    * (
                        args.per_account * 10
                        - sum(i % 10 in (8, 9) for i in range(args.per_account))
                    ),
                    results=results,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
