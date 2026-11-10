"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { Activity } from "lucide-react";
import { DataState, PageHeader, Section, StatusIndicator, type ProductStatus } from "@/components/aven";
import { Alert, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import { api, formatDate } from "@/lib/api";
import type { AwsAccount, CollectionRun, Scan } from "@/lib/types";
import styles from "./scans.module.css";

function statusPresentation(status: string, labels: Record<string, string>): { status: ProductStatus; label: string } {
  const normalized = status.trim().toUpperCase();
  if (normalized === "SUCCESS" || normalized === "COMPLETED") return { status: "success", label: labels.completed };
  if (normalized === "FAILED" || normalized === "ERROR") return { status: "danger", label: labels.failed };
  if (normalized === "RUNNING" || normalized === "PENDING") return { status: "pending", label: normalized === "RUNNING" ? labels.running : labels.pending };
  if (normalized === "COMPLETED_WITH_WARNINGS") return { status: "warning", label: labels.warnings };
  return { status: "neutral", label: status || labels.unknown };
}

export default function ScansPage() {
  const locale = useLocale();
  const t = useTranslations("scans");
  const labels = {completed: t("status.completed"), failed: t("status.failed"), running: t("status.running"), pending: t("status.pending"), warnings: t("status.warnings"), unknown: t("status.unknown")};
  const [scans, setScans] = useState<Scan[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [collections, setCollections] = useState<CollectionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = () =>
      Promise.all([
        api<Scan[]>("/scans?limit=100"),
        api<AwsAccount[]>("/accounts"),
        api<CollectionRun[]>("/collections?limit=200"),
      ])
        .then(([scanData, accountData, collectionData]) => {
          if (!active) return;
          setScans(scanData);
          setAccounts(accountData);
          setCollections(collectionData);
          setError("");
        })
        .catch((err) => {
          if (active) setError(err instanceof Error ? err.message : "ERR_SCANS_LOAD");
        })
        .finally(() => {
          if (active) setLoading(false);
        });

    void load();
    const timer = window.setInterval(load, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const accountNames = useMemo(
    () => Object.fromEntries(accounts.map((account) => [account.id, account.name])),
    [accounts],
  );
  const collectionByScan = useMemo(
    () =>
      Object.fromEntries(
        collections
          .filter((run) => run.scan_id)
          .map((run) => [run.scan_id as string, run]),
      ),
    [collections],
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        metadata={t("metadata")}
      />

      {error && <Alert variant="danger" title={t("loadError")} description={error === "ERR_SCANS_LOAD" ? t("loadError") : error} />}

      <Section
        appearance="card"
        title={t("awsScans")}
        description={t("awsDescription")}
        actions={<Activity {...iconDefaults} aria-hidden="true" />}
      >
        <DataState
          loading={loading && scans.length === 0}
          empty={!loading && scans.length === 0}
          emptyTitle={t("emptyTitle")}
          emptyDescription={t("emptyDescription")}
        >
          <Table aria-label={t("tableLabel")}>
            <TableHeader>
              <TableRow staticRow>
                <TableHead>{t("column.account")}</TableHead>
                <TableHead>{t("column.trigger")}</TableHead>
                <TableHead>{t("column.started")}</TableHead>
                <TableHead>{t("column.finished")}</TableHead>
                <TableHead numeric>{t("column.findings")}</TableHead>
                <TableHead>{t("column.status")}</TableHead>
                <TableHead>{t("column.collection")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {scans.map((scan) => {
                const run = collectionByScan[scan.id];
                const scanStatus = statusPresentation(scan.status, labels);
                const runStatus = run ? statusPresentation(run.status, labels) : null;
                return (
                  <TableRow key={scan.id}>
                    <TableCell>
                      <span className={styles.cellStack}>
                        <strong className={styles.primaryText}>{accountNames[scan.account_id] || t("account", {id: scan.account_id})}</strong>
                        <span className={styles.secondaryText}>{scan.id.slice(0, 8)}</span>
                      </span>
                    </TableCell>
                    <TableCell>{scan.trigger === "manual" ? t("trigger.manual") : t("trigger.scheduled")}</TableCell>
                    <TableCell>{formatDate(scan.started_at || scan.created_at, locale)}</TableCell>
                    <TableCell>{formatDate(scan.completed_at, locale)}</TableCell>
                    <TableCell numeric>{scan.findings_count}</TableCell>
                    <TableCell>
                      <span className={styles.cellStack}>
                        <StatusIndicator status={scanStatus.status} label={scanStatus.label} />
                        {scan.error && <span className={styles.secondaryText} title={scan.error}>{t("detailError")}</span>}
                      </span>
                    </TableCell>
                    <TableCell>
                      {run && runStatus ? (
                        <div className={styles.rowActions}>
                          <Link className={styles.link} href={`/collections/${run.id}`}>{t("viewCollection")}</Link>
                          {run.status === "SUCCESS" && (
                            <Link className={styles.link} href={`/collections/${run.id}/compare`}>{t("compare")}</Link>
                          )}
                          <StatusIndicator status={runStatus.status} label={runStatus.label} />
                        </div>
                      ) : (
                        <span className={styles.secondaryText}>{t("noCollectionRun")}</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </DataState>
      </Section>
    </div>
  );
}
