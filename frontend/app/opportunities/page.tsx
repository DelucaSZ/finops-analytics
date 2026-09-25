"use client";

import { Fragment, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BrainCircuit, Building2, Filter, Search, Tags, WalletCards, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { FindingEvidence } from "@/components/finding-evidence";
import { findingExplanation } from "@/lib/finding-explanation";
import { api, formatDate, usd } from "@/lib/api";
import type { AwsAccount, Finding } from "@/lib/types";

export default function OpportunitiesPage() {
  return <Suspense fallback={<p role="status">Carregando oportunidades…</p>}><OpportunitiesContent /></Suspense>;
}

function OpportunitiesContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [ruleOptions, setRuleOptions] = useState<[string, string][]>([]);
  const [query, setQuery] = useState("");
  const priority = searchParams.get("severity") || "all";
  const severity = ["high", "medium", "low"].includes(priority) ? priority : "all";
  const accountId = searchParams.get("account_id") || "all";
  const ruleKey = searchParams.get("rule_key") || "all";
  const status = ["open", "treated", "rejected"].includes(searchParams.get("status") || "") ? searchParams.get("status")! : "open";
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const [aiInsight, setAiInsight] = useState<{ title: string; text: string } | null>(null);
  const [aiLoading, setAiLoading] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function loadFindings() {
      const all: Finding[] = [];
      const limit = 500;
      for (let offset = 0; ; offset += limit) {
        const page = await api<Finding[]>(`/findings?status=${status}&limit=${limit}&offset=${offset}`, { signal: controller.signal });
        all.push(...page);
        if (page.length < limit) return [...new Map(all.map((item) => [item.id, item])).values()];
      }
    }
    Promise.all([loadFindings(), api<AwsAccount[]>("/accounts", { signal: controller.signal })])
      .then(([findingData, accountData]) => {
        setFindings(findingData); setAccounts(accountData);
        const rules = new Map(findingData.map((finding) => [finding.rule_key, finding.title]));
        rules.set("missing_required_tags", "Recursos sem tags obrigatórias");
        setRuleOptions([...rules.entries()].sort((a, b) => a[1].localeCompare(b[1], "pt-BR")));
      })
      .catch((err) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Falha ao carregar"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [status]);

  const accountNames = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a.name])), [accounts]);
  const filtered = useMemo(() => findings.filter((finding) => {
    const text = `${finding.title} ${finding.resource_id} ${finding.resource_name || ""}`.toLowerCase();
    return text.includes(query.toLowerCase())
      && (severity === "all" || finding.severity === severity)
      && (accountId === "all" || String(finding.account_id) === accountId)
      && (ruleKey === "all" || finding.rule_key === ruleKey);
  }), [findings, query, severity, accountId, ruleKey]);
  // Only visible selections are actionable, including during URL/back navigation.
  const selected = filtered.filter((finding) => selectedIds.has(finding.id));
  const allSelected = filtered.length > 0 && selected.length === filtered.length;
  const total = filtered.reduce((sum, finding) => sum + Number(finding.estimated_monthly_savings), 0);

  useEffect(() => { setSelectedIds(new Set()); }, [query, severity, accountId, ruleKey, status]);
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = selected.length > 0 && !allSelected;
  }, [selected.length, allSelected]);

  function changeFilter(key: string, value: string) {
    setSelectedIds(new Set());
    const params = new URLSearchParams(searchParams.toString());
    if (value === "all") params.delete(key); else params.set(key, value);
    router.replace(`${pathname}${params.size ? `?${params}` : ""}`, { scroll: false });
  }

  function toggleSelection(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function lifecycle(ids: string[], action: "treat" | "reject" | "reopen") {
    if (!ids.length || savingRef.current) return;
    let reason: string | undefined;
    let note: string | undefined;
    if (action === "reject") {
      reason = window.prompt("Motivo: FALSE_POSITIVE, OPERATIONAL_EXCEPTION, ACCEPTABLE_COST, RESOURCE_REQUIRED, RISK_ACCEPTED ou OTHER") || undefined;
      if (!reason) return;
      note = window.prompt("Observação (obrigatória para OTHER):") || undefined;
    } else {
      note = window.prompt(action === "treat" ? "Observação do tratamento (opcional):" : "Motivo/observação da reabertura (opcional):") || undefined;
    }
    savingRef.current = true;
    setSaving(true); setError(""); setMessage("");
    try {
      const result = await api<{ updated_ids: string[]; updated_count: number }>("/findings/bulk/action", {
        method: "POST", body: JSON.stringify({ finding_ids: ids, action, reason, note }),
      });
      const updated = new Set(result.updated_ids);
      setFindings((current) => current.filter((item) => !updated.has(item.id)));
      setSelectedIds(new Set());
      setMessage(`${result.updated_count} oportunidade(s) atualizada(s) com sucesso.`);
    } catch (err) { setError(err instanceof Error ? err.message : "Falha ao atualizar oportunidades"); }
    finally { savingRef.current = false; setSaving(false); }
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
      {message && <div className="alert success" role="status">{message}</div>}
      {aiInsight && <section className="ai-insight"><div className="ai-insight-heading"><span><BrainCircuit size={18} /> Análise por IA · {aiInsight.title}</span><button aria-label="Fechar análise por IA" onClick={() => setAiInsight(null)}><X size={16} /></button></div><div className="ai-insight-body">{aiInsight.text}</div></section>}
      <section className="summary-strip">
        <div><WalletCards size={20} /><span>Economia exibida</span><strong>{usd(total)}/mês</strong></div>
        <div><span>Resultados</span><strong>{loading ? "…" : filtered.length}</strong></div>
      </section>
      <section className="panel table-panel" aria-busy={loading || saving}>
        <div className="toolbar opportunities-toolbar">
          <label className="search-field"><Search size={16} /><input disabled={saving} aria-label="Buscar recurso ou oportunidade" placeholder="Buscar recurso ou oportunidade" value={query} onChange={(e) => { setSelectedIds(new Set()); setQuery(e.target.value); }} /></label>
          <label className="select-field"><Building2 size={16} /><select disabled={saving} aria-label="Filtrar por conta" value={accountId} onChange={(e) => changeFilter("account_id", e.target.value)}><option value="all">Todas as contas</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.aws_account_id}</option>)}</select></label>
          <label className="select-field"><Filter size={16} /><select disabled={saving} aria-label="Filtrar por prioridade" value={severity} onChange={(e) => changeFilter("severity", e.target.value)}><option value="all">Todas as prioridades</option><option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option></select></label>
          <label className="select-field"><select disabled={saving} aria-label="Filtrar por status" value={status} onChange={(e) => changeFilter("status", e.target.value)}><option value="open">Abertas</option><option value="treated">Tratadas</option><option value="rejected">Rejeitadas</option></select></label>\n          <label className="select-field"><Tags size={16} /><select disabled={saving} aria-label="Filtrar por tipo de oportunidade" value={ruleKey} onChange={(e) => changeFilter("rule_key", e.target.value)}><option value="all">Todos os tipos</option>{ruleOptions.map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
        </div>
        <div className="bulk-toolbar">
          <label className="selection-control"><input ref={selectAllRef} type="checkbox" checked={allSelected} disabled={loading || saving || !filtered.length} onChange={() => setSelectedIds(allSelected ? new Set() : new Set(filtered.map((finding) => finding.id)))} /> Selecionar todos os resultados filtrados ({filtered.length})</label>
          <span role="status">{selected.length} selecionada(s)</span>
          <div className="bulk-actions">
            <button className="button ghost" disabled={saving || !selected.length} onClick={() => setSelectedIds(new Set())}>Limpar seleção</button>
            {status === "open" ? <><button className="button ghost" disabled={saving || !selected.length} onClick={() => void lifecycle(selected.map((item) => item.id), "treat")}>Marcar como tratadas</button><button className="button primary" disabled={saving || !selected.length} onClick={() => void lifecycle(selected.map((item) => item.id), "reject")}>{saving ? "Aplicando…" : "Rejeitar selecionadas"}</button></> : <button className="button primary" disabled={saving || !selected.length} onClick={() => void lifecycle(selected.map((item) => item.id), "reopen")}>Reabrir selecionadas</button>}
          </div>
        </div>
        <div className="data-table-wrap" role="region" aria-label="Oportunidades encontradas" tabIndex={0}>
          <table className="data-table opportunities-table" aria-label="Oportunidades de economia">
            <thead><tr><th scope="col" className="selection-cell">Seleção</th><th scope="col">Oportunidade</th><th scope="col">Conta / Região</th><th scope="col">Prioridade</th><th scope="col">Economia</th><th scope="col">Última validação</th><th scope="col">Ações</th></tr></thead>
            <tbody>
              {filtered.map((finding) => (
                <Fragment key={finding.id}>
                <tr className={selectedIds.has(finding.id) ? "selected-row" : undefined}>
                  <td className="selection-cell"><label className="selection-control"><input type="checkbox" aria-label={`Selecionar ${finding.title} · ${finding.resource_id}`} checked={selectedIds.has(finding.id)} disabled={saving} onChange={() => toggleSelection(finding.id)} /></label></td>
                  <td><strong>{finding.title}</strong><span>{finding.resource_name || finding.resource_id}</span>
                    <p className="finding-reason">{findingExplanation(finding).summary}</p>
                    <button className="evidence-toggle" aria-expanded={expandedIds.has(finding.id)} aria-controls={`evidence-${finding.id}`} aria-label={`${expandedIds.has(finding.id) ? "Ocultar" : "Ver"} evidências de ${finding.title} · ${finding.resource_id}`} onClick={() => setExpandedIds((current) => {
                      const next = new Set(current);
                      if (next.has(finding.id)) next.delete(finding.id); else next.add(finding.id);
                      return next;
                    })}>{expandedIds.has(finding.id) ? "Ocultar evidências" : "Ver evidências"}</button>
                  </td>
                  <td><strong>{accountNames[finding.account_id] || `Conta ${finding.account_id}`}</strong><span>{finding.region} · {finding.service}</span></td>
                  <td><StatusBadge value={finding.severity} /></td>
                  <td className="money-cell">{finding.rule_key === "cost_growth_anomaly" ? <><span>Não estimada</span></> : <>{usd(finding.estimated_monthly_savings)}<span>/mês</span></>}</td>
                  <td className="date-cell">{formatDate(finding.last_seen_at)}</td>
                  <td><div className="row-actions"><StatusBadge value={finding.status} />{finding.needs_review && <span>Detectada novamente</span>}<button onClick={() => void explain(finding)} disabled={saving || aiLoading !== null}>{aiLoading === finding.id ? "Analisando…" : "Analisar IA"}</button>{finding.status === "open" ? <><button disabled={saving} onClick={() => void lifecycle([finding.id], "treat")}>Marcar como tratado</button><button disabled={saving} onClick={() => void lifecycle([finding.id], "reject")}>Rejeitar</button></> : <button disabled={saving} onClick={() => void lifecycle([finding.id], "reopen")}>Reabrir</button>}</div></td>
                </tr>
                {expandedIds.has(finding.id) && <tr className="evidence-row" id={`evidence-${finding.id}`}><td colSpan={7}><FindingEvidence finding={finding} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
          {loading ? <div className="empty-table" role="status">Carregando todas as oportunidades…</div> : !filtered.length && <div className="empty-table">{error ? "Não foi possível carregar as oportunidades. Recarregue a página para tentar novamente." : "Nenhuma oportunidade corresponde aos filtros."}</div>}
        </div>
      </section>
    </>
  );
}
