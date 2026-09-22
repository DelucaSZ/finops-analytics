"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Building2,
  CircleDollarSign,
  CloudLightning,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate, usd } from "@/lib/api";
import type { AwsAccount, DashboardSummary } from "@/lib/types";

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [summaryData, accountData] = await Promise.all([
        api<DashboardSummary>("/dashboard/summary"),
        api<AwsAccount[]>("/accounts"),
      ]);
      setSummary(summaryData);
      setAccounts(accountData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar o dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const accountNames = useMemo(
    () => Object.fromEntries(accounts.map((account) => [account.id, account.name])),
    [accounts],
  );

  return (
    <>
      <PageHeader
        eyebrow="VISÃO CONSOLIDADA"
        title="Eficiência da nuvem"
        description="Desperdícios, economia potencial e saúde das contas AWS em um só lugar."
        actions={
          <>
            <button className="button ghost" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={16} className={loading ? "spin" : ""} /> Atualizar
            </button>
            <Link className="button primary" href="/accounts">Executar análise <ArrowRight size={16} /></Link>
          </>
        }
      />

      {error && <div className="alert error">{error}</div>}

      <section className="metrics-grid">
        <article className="metric-card featured">
          <div className="metric-icon"><CircleDollarSign size={21} /></div>
          <span>Economia potencial mensal</span>
          <strong>{usd(summary?.estimated_monthly_savings_usd || 0)}</strong>
          <small>{usd(summary?.estimated_annual_savings_usd || 0)} por ano</small>
          <div className="metric-glow" />
        </article>
        <article className="metric-card">
          <div className="metric-icon violet"><CloudLightning size={21} /></div>
          <span>Oportunidades abertas</span>
          <strong>{summary?.open_findings || 0}</strong>
          <small>{summary?.by_severity?.high || 0} de alta prioridade</small>
        </article>
        <article className="metric-card">
          <div className="metric-icon blue"><Building2 size={21} /></div>
          <span>Contas monitoradas</span>
          <strong>{summary?.accounts || 0}</strong>
          <small>{summary?.connected_accounts || 0} com conexão validada</small>
        </article>
        <article className="metric-card">
          <div className="metric-icon green"><ShieldCheck size={21} /></div>
          <span>Cobertura inicial</span>
          <strong>9/9</strong>
          <small>regras do MVP implementadas</small>
        </article>
      </section>

      <section className="dashboard-grid">
        <article className="panel opportunities-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">MAIOR IMPACTO</span><h2>Oportunidades prioritárias</h2></div>
            <Link href="/opportunities">Ver todas <ArrowRight size={15} /></Link>
          </div>
          {!summary?.top_findings.length ? (
            <EmptyState icon={<Sparkles />} title="Nenhuma oportunidade encontrada" text="Cadastre uma conta e execute a primeira análise." />
          ) : (
            <div className="opportunity-list">
              {summary.top_findings.map((finding) => (
                <div className="opportunity-row" key={finding.id}>
                  <div className={`severity-dot ${finding.severity}`} />
                  <div className="opportunity-main">
                    <strong>{finding.title}</strong>
                    <span>{finding.resource_id} · {finding.region} · {accountNames[finding.account_id] || `Conta ${finding.account_id}`}</span>
                  </div>
                  <StatusBadge value={finding.severity} />
                  <div className="opportunity-value"><strong>{usd(finding.estimated_monthly_savings_usd)}</strong><span>/mês</span></div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="panel severity-panel">
          <div className="panel-heading"><div><span className="eyebrow">RISCO E IMPACTO</span><h2>Prioridade</h2></div></div>
          <div className="severity-chart">
            {[{ key: "high", label: "Alta", color: "#ff6b72" }, { key: "medium", label: "Média", color: "#f9bd4f" }, { key: "low", label: "Baixa", color: "#51d7aa" }].map((item) => {
              const value = summary?.by_severity?.[item.key] || 0;
              const total = Math.max(summary?.open_findings || 1, 1);
              return (
                <div className="severity-line" key={item.key}>
                  <div><span>{item.label}</span><strong>{value}</strong></div>
                  <div className="bar-track"><div style={{ width: `${Math.max(value ? 8 : 0, (value / total) * 100)}%`, background: item.color }} /></div>
                </div>
              );
            })}
          </div>
          <div className="insight-box"><TriangleAlert size={18} /><p><strong>Leitura rápida</strong>Comece pelas oportunidades de alta prioridade e maior economia mensal.</p></div>
        </article>

        <article className="panel scans-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">ATIVIDADE</span><h2>Últimas execuções</h2></div>
            <Link href="/scans">Histórico <ArrowRight size={15} /></Link>
          </div>
          {!summary?.latest_scans.length ? (
            <EmptyState icon={<RefreshCw />} title="Ainda sem execuções" text="A primeira análise aparecerá aqui." />
          ) : (
            <div className="simple-list">
              {summary.latest_scans.map((scan) => (
                <div key={scan.id}>
                  <span className="scan-account">{accountNames[scan.account_id] || `Conta ${scan.account_id}`}</span>
                  <span>{formatDate(scan.created_at)}</span>
                  <span>{scan.findings_count} achados</span>
                  <StatusBadge value={scan.status} />
                </div>
              ))}
            </div>
          )}
        </article>
      </section>
    </>
  );
}

function EmptyState({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="empty-state"><span>{icon}</span><strong>{title}</strong><p>{text}</p></div>;
}
