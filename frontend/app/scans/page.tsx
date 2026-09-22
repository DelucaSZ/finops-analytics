"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate } from "@/lib/api";
import type { AwsAccount, Scan } from "@/lib/types";

export default function ScansPage() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () => Promise.all([api<Scan[]>("/scans?limit=100"), api<AwsAccount[]>("/accounts")])
      .then(([scanData, accountData]) => { setScans(scanData); setAccounts(accountData); })
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar"));
    void load();
    const timer = window.setInterval(load, 10000);
    return () => window.clearInterval(timer);
  }, []);

  const accountNames = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a.name])), [accounts]);
  return (
    <>
      <PageHeader eyebrow="PROCESSAMENTO" title="Execuções" description="Histórico das análises manuais e agendadas." />
      {error && <div className="alert error">{error}</div>}
      <section className="panel table-panel">
        <div className="panel-heading"><div><span className="eyebrow">HISTÓRICO</span><h2>Varreduras AWS</h2></div><Activity size={20} /></div>
        <div className="data-table-wrap">
          <table className="data-table"><thead><tr><th>Conta</th><th>Gatilho</th><th>Início</th><th>Conclusão</th><th>Achados</th><th>Status</th></tr></thead>
            <tbody>{scans.map((scan) => <tr key={scan.id}><td><strong>{accountNames[scan.account_id] || `Conta ${scan.account_id}`}</strong><span>{scan.id.slice(0, 8)}</span></td><td>{scan.trigger === "manual" ? "Manual" : "Agendada"}</td><td>{formatDate(scan.started_at || scan.created_at)}</td><td>{formatDate(scan.completed_at)}</td><td>{scan.findings_count}</td><td><StatusBadge value={scan.status} />{scan.error && <span className="error-hint" title={scan.error}>ver erro</span>}</td></tr>)}</tbody>
          </table>
          {!scans.length && <div className="empty-table">Nenhuma análise executada até agora.</div>}
        </div>
      </section>
    </>
  );
}
