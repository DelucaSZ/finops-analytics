"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate } from "@/lib/api";
import type { AwsAccount, CollectionRun, Scan } from "@/lib/types";

function collectionStatus(status: string) {
  if (status === "SUCCESS") return "completed";
  return status.toLowerCase();
}

export default function ScansPage() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [collections, setCollections] = useState<CollectionRun[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      Promise.all([
        api<Scan[]>("/scans?limit=100"),
        api<AwsAccount[]>("/accounts"),
        api<CollectionRun[]>("/collections?limit=200"),
      ])
        .then(([scanData, accountData, collectionData]) => {
          setScans(scanData);
          setAccounts(accountData);
          setCollections(collectionData);
          setError("");
        })
        .catch(() => setError("Não foi possível carregar as análises. Tente novamente."))
        .finally(() => setLoading(false));
    void load();
    const timer = window.setInterval(load, 10000);
    return () => window.clearInterval(timer);
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
    <>
      <PageHeader
        eyebrow="PROCESSAMENTO"
        title="Análises AWS"
        description="Histórico das análises manuais e agendadas, com acesso à coleta auditável correspondente."
      />
      {error && <div className="alert error" role="alert">{error}</div>}
      <section className="panel table-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">HISTÓRICO</span>
            <h2>Histórico de análises</h2>
          </div>
          <Activity size={20} />
        </div>
        <div
          className="data-table-wrap"
          role="region"
          aria-label="Histórico de execuções"
          tabIndex={0}
        >
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Conta</th>
                <th scope="col">Gatilho</th>
                <th scope="col">Início</th>
                <th scope="col">Conclusão</th>
                <th scope="col">Achados</th>
                <th scope="col">Status</th>
                <th scope="col">Coleta</th>
              </tr>
            </thead>
            <tbody>
              {loading && Array.from({ length: 5 }, (_, row) => (
                <tr key={`loading-${row}`} aria-hidden="true">
                  {Array.from({ length: 7 }, (_, cell) => (
                    <td key={cell}><span className="skeleton-box skeleton-line" /></td>
                  ))}
                </tr>
              ))}
              {!loading && scans.map((scan) => {
                const run = collectionByScan[scan.id];
                return (
                  <tr key={scan.id}>
                    <td>
                      <strong>{accountNames[scan.account_id] || `Conta ${scan.account_id}`}</strong>
                      <span>{scan.id.slice(0, 8)}</span>
                    </td>
                    <td>{scan.trigger === "manual" ? "Manual" : "Agendada"}</td>
                    <td>{formatDate(scan.started_at || scan.created_at)}</td>
                    <td>{formatDate(scan.completed_at)}</td>
                    <td>{scan.findings_count}</td>
                    <td>
                      <StatusBadge value={scan.status} />
                      {scan.error && (
                        <span className="error-hint" title={scan.error}>
                          ver erro
                        </span>
                      )}
                    </td>
                    <td>
                      {run ? (
                        <div className="row-actions">
                          <Link href={`/collections/${run.id}`}>Ver coleta</Link>
                          {run.status === "SUCCESS" && (
                            <Link href={`/collections/${run.id}/compare`}>Comparar</Link>
                          )}
                          <StatusBadge value={collectionStatus(run.status)} />
                        </div>
                      ) : (
                        <span>Sem coleta vinculada</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && !error && !scans.length && <div className="empty-table">Nenhuma análise executada até agora.</div>}
        </div>
      </section>
    </>
  );
}
