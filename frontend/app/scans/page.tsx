"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity } from "lucide-react";
import { DataState, PageHeader, Section, StatusIndicator, type ProductStatus } from "@/components/aven";
import { Alert, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import { api, formatDate } from "@/lib/api";
import type { AwsAccount, CollectionRun, Scan } from "@/lib/types";
import styles from "./scans.module.css";

function statusPresentation(status: string): { status: ProductStatus; label: string } {
  const normalized = status.trim().toUpperCase();
  if (normalized === "SUCCESS" || normalized === "COMPLETED") return { status: "success", label: "Concluída" };
  if (normalized === "FAILED" || normalized === "ERROR") return { status: "danger", label: "Falhou" };
  if (normalized === "RUNNING" || normalized === "PENDING") return { status: "pending", label: normalized === "RUNNING" ? "Em andamento" : "Pendente" };
  if (normalized === "COMPLETED_WITH_WARNINGS") return { status: "warning", label: "Com alertas" };
  return { status: "neutral", label: status || "Desconhecido" };
}

export default function ScansPage() {
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
          if (active) setError(err instanceof Error ? err.message : "Falha ao carregar execuções.");
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
        title="Execuções"
        description="Histórico das análises manuais e agendadas, com acesso ao CollectionRun auditável."
        metadata="Processamento · atualização operacional a cada 10 segundos"
      />

      {error && <Alert variant="danger" title="Não foi possível atualizar as execuções" description={error} />}

      <Section
        appearance="card"
        title="Varreduras AWS"
        description="Execuções persistidas e o CollectionRun correspondente quando disponível."
        actions={<Activity {...iconDefaults} aria-hidden="true" />}
      >
        <DataState
          loading={loading && scans.length === 0}
          empty={!loading && scans.length === 0}
          emptyTitle="Nenhuma análise executada"
          emptyDescription="O histórico aparecerá aqui após uma execução real."
        >
          <Table aria-label="Histórico de execuções">
            <TableHeader>
              <TableRow staticRow>
                <TableHead>Conta</TableHead>
                <TableHead>Gatilho</TableHead>
                <TableHead>Início</TableHead>
                <TableHead>Conclusão</TableHead>
                <TableHead numeric>Achados</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Coleta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {scans.map((scan) => {
                const run = collectionByScan[scan.id];
                const scanStatus = statusPresentation(scan.status);
                const runStatus = run ? statusPresentation(run.status) : null;
                return (
                  <TableRow key={scan.id}>
                    <TableCell>
                      <span className={styles.cellStack}>
                        <strong className={styles.primaryText}>{accountNames[scan.account_id] || `Conta ${scan.account_id}`}</strong>
                        <span className={styles.secondaryText}>{scan.id.slice(0, 8)}</span>
                      </span>
                    </TableCell>
                    <TableCell>{scan.trigger === "manual" ? "Manual" : "Agendada"}</TableCell>
                    <TableCell>{formatDate(scan.started_at || scan.created_at)}</TableCell>
                    <TableCell>{formatDate(scan.completed_at)}</TableCell>
                    <TableCell numeric>{scan.findings_count}</TableCell>
                    <TableCell>
                      <span className={styles.cellStack}>
                        <StatusIndicator status={scanStatus.status} label={scanStatus.label} />
                        {scan.error && <span className={styles.secondaryText} title={scan.error}>Erro disponível nos detalhes da execução.</span>}
                      </span>
                    </TableCell>
                    <TableCell>
                      {run && runStatus ? (
                        <div className={styles.rowActions}>
                          <Link className={styles.link} href={`/collections/${run.id}`}>Ver coleta</Link>
                          {run.status === "SUCCESS" && (
                            <Link className={styles.link} href={`/collections/${run.id}/compare`}>Comparar</Link>
                          )}
                          <StatusIndicator status={runStatus.status} label={runStatus.label} />
                        </div>
                      ) : (
                        <span className={styles.secondaryText}>Sem CollectionRun</span>
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
