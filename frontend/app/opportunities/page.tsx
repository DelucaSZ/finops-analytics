"use client";

import { useEffect, useMemo, useState } from "react";
import { BrainCircuit, Filter, Search, WalletCards, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate, usd } from "@/lib/api";
import type { AwsAccount, Finding } from "@/lib/types";

export default function OpportunitiesPage() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [error, setError] = useState("");
  const [aiInsight, setAiInsight] = useState<{ title: string; text: string } | null>(null);
  const [aiLoading, setAiLoading] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<Finding[]>("/findings?status=open"), api<AwsAccount[]>("/accounts")])
      .then(([findingData, accountData]) => { setFindings(findingData); setAccounts(accountData); })
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar"));
  }, []);

  const accountNames = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a.name])), [accounts]);
  const filtered = findings.filter((finding) => {
    const text = `${finding.title} ${finding.resource_id} ${finding.resource_name || ""}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (severity === "all" || finding.severity === severity);
  });
  const total = filtered.reduce((sum, finding) => sum + Number(finding.estimated_monthly_savings), 0);

  async function changeStatus(id: string, status: string) {
    await api(`/findings/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
    setFindings((current) => current.filter((item) => item.id !== id));
  }

  async function explain(finding: Finding) {
    setAiLoading(finding.id); setError("");
    try {
      const result = await api<{ explanation: string }>(`/findings/${finding.id}/explain`, { method: "POST" });
      setAiInsight({ title: finding.title, text: result.explanation });
    } catch (err) { setError(err instanceof Error ? err.message : "Falha na análise por IA"); }
    finally { setAiLoading(null); }
  }

  return (
    <>
      <PageHeader eyebrow="ANÁLISES" title="Oportunidades" description="Evidências técnicas e economia estimada por recurso." />
      {error && <div className="alert error" role="alert">{error}</div>}
      {aiInsight && <section className="ai-insight"><div className="ai-insight-heading"><span><BrainCircuit size={18} /> Análise por IA · {aiInsight.title}</span><button aria-label="Fechar análise por IA" onClick={() => setAiInsight(null)}><X size={16} /></button></div><div className="ai-insight-body">{aiInsight.text}</div></section>}
      <section className="summary-strip">
        <div><WalletCards size={20} /><span>Economia exibida</span><strong>{usd(total)}/mês</strong></div>
        <div><span>Resultados</span><strong>{filtered.length}</strong></div>
      </section>
      <section className="panel table-panel">
        <div className="toolbar">
          <label className="search-field"><Search size={16} /><input aria-label="Buscar recurso ou oportunidade" placeholder="Buscar recurso ou oportunidade" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
          <label className="select-field"><Filter size={16} /><select aria-label="Filtrar por prioridade" value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="all">Todas as prioridades</option><option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option></select></label>
        </div>
        <div className="data-table-wrap" role="region" aria-label="Oportunidades encontradas" tabIndex={0}>
          <table className="data-table" aria-label="Oportunidades de economia">
            <thead><tr><th scope="col">Oportunidade</th><th scope="col">Conta / Região</th><th scope="col">Prioridade</th><th scope="col">Economia</th><th scope="col">Última validação</th><th scope="col">Ações</th></tr></thead>
            <tbody>
              {filtered.map((finding) => (
                <tr key={finding.id}>
                  <td><strong>{finding.title}</strong><span>{finding.resource_name || finding.resource_id}</span></td>
                  <td><strong>{accountNames[finding.account_id] || `Conta ${finding.account_id}`}</strong><span>{finding.region} · {finding.service}</span></td>
                  <td><StatusBadge value={finding.severity} /></td>
                  <td className="money-cell">{usd(finding.estimated_monthly_savings)}<span>/mês</span></td>
                  <td className="date-cell">{formatDate(finding.last_seen_at)}</td>
                  <td><div className="row-actions"><button onClick={() => void explain(finding)} disabled={aiLoading === finding.id}>{aiLoading === finding.id ? "Analisando…" : "Analisar IA"}</button><button onClick={() => void changeStatus(finding.id, "accepted")}>Aceitar</button><button onClick={() => void changeStatus(finding.id, "dismissed")}>Ignorar</button></div></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filtered.length && <div className="empty-table">Nenhuma oportunidade corresponde aos filtros.</div>}
        </div>
      </section>
    </>
  );
}
