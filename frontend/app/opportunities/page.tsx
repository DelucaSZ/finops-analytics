"use client";

import { Fragment, Suspense, useDeferredValue, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  BrainCircuit,
  Building2,
  Filter,
  Search,
  Tags,
  WalletCards,
  X,
} from "lucide-react";
import { FindingEvidence } from "@/components/finding-evidence";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate, usd } from "@/lib/api";
import { findingExplanation } from "@/lib/finding-explanation";
import type { AwsAccount, Finding, OpportunityPage, Policy } from "@/lib/types";

const PAGE_SIZE = 50;

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<p role="status">Carregando oportunidades…</p>}>
      <OpportunitiesContent />
    </Suspense>
  );
}

function OpportunitiesContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [ruleOptions, setRuleOptions] = useState<[string, string][]>([]);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim());
  const priority = searchParams.get("severity") || "all";
  const severity = ["high", "medium", "low"].includes(priority) ? priority : "all";
  const accountId = searchParams.get("account_id") || "all";
  const ruleKey = searchParams.get("rule_key") || "all";
  const requestedStatus = searchParams.get("status") || "";
  const status = ["open", "treated", "rejected"].includes(requestedStatus)
    ? requestedStatus
    : "open";
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
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
    Promise.all([
      api<AwsAccount[]>("/accounts", { signal: controller.signal }),
      api<Policy[]>("/policies/global", { signal: controller.signal }),
    ])
      .then(([accountData, policies]) => {
        setAccounts(accountData);
        setRuleOptions(
          policies
            .map((policy) => [policy.rule_key, policy.name] as [string, string])
            .sort((a, b) => a[1].localeCompare(b[1], "pt-BR")),
        );
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Falha ao carregar filtros");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      status,
      page: String(page),
      page_size: String(PAGE_SIZE),
      sort: "last_seen_at",
      order: "desc",
    });
    if (severity !== "all") params.set("severity", severity);
    if (accountId !== "all") params.set("account_id", accountId);
    if (ruleKey !== "all") params.set("rule", ruleKey);
    if (deferredQuery) params.set("search", deferredQuery);

    setLoading(true);
    setError("");
    api<OpportunityPage>(`/opportunities?${params}`, { signal: controller.signal })
      .then((data) => {
        setFindings(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setSelectedIds(new Set());
        if (data.total_pages > 0 && page > data.total_pages) {
          setPage(data.total_pages);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Falha ao carregar oportunidades");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [accountId, deferredQuery, page, reloadKey, ruleKey, severity, status]);

  const selected = findings.filter((finding) => selectedIds.has(finding.id));
  const allSelected = findings.length > 0 && selected.length === findings.length;
  const totalSavings = findings.reduce(
    (sum, finding) => sum + Number(finding.estimated_monthly_savings),
    0,
  );

  useEffect(() => {
    setPage(1);
    setSelectedIds(new Set());
  }, [deferredQuery]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selected.length > 0 && !allSelected;
    }
  }, [allSelected, selected.length]);

  function changeFilter(key: string, value: string) {
    setPage(1);
    setSelectedIds(new Set());
    const params = new URLSearchParams(searchParams.toString());
    if (value === "all") params.delete(key);
    else params.set(key, value);
    router.replace(`${pathname}${params.size ? `?${params}` : ""}`, { scroll: false });
  }

  function toggleSelection(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function lifecycle(ids: string[], action: "treat" | "reject" | "reopen") {
    if (!ids.length || savingRef.current) return;
    let reason: string | undefined;
    let note: string | undefined;
    if (action === "reject") {
      reason =
        window.prompt(
          "Motivo: FALSE_POSITIVE, OPERATIONAL_EXCEPTION, ACCEPTABLE_COST, " +
            "RESOURCE_REQUIRED, RISK_ACCEPTED ou OTHER",
        ) || undefined;
      if (!reason) return;
      note = window.prompt("Observação (obrigatória para OTHER):") || undefined;
    } else {
      note =
        window.prompt(
          action === "treat"
            ? "Observação do tratamento (opcional):"
            : "Motivo/observação da reabertura (opcional):",
        ) || undefined;
    }

    savingRef.current = true;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ updated: number }>(`/opportunities/bulk/${action}`, {
        method: "POST",
        body: JSON.stringify({ opportunity_ids: ids, reason, note }),
      });
      setSelectedIds(new Set());
      setMessage(`${result.updated} oportunidade(s) atualizada(s) com sucesso.`);
      setReloadKey((current) => current + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar oportunidades");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  async function explain(finding: Finding) {
    setAiLoading(finding.id);
    setError("");
    try {
      const result = await api<{ explanation: string }>(`/findings/${finding.id}/explain`, {
        method: "POST",
      });
      setAiInsight({ title: finding.title, text: result.explanation });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha na análise por IA");
    } finally {
      setAiLoading(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="ANÁLISES"
        title="Oportunidades"
        description="Evidências técnicas e economia estimada por recurso."
      />
      {error && <div className="alert error" role="alert">{error}</div>}
      {message && <div className="alert success" role="status">{message}</div>}
      {aiInsight && (
        <section className="ai-insight">
          <div className="ai-insight-heading">
            <span><BrainCircuit size={18} /> Análise por IA · {aiInsight.title}</span>
            <button aria-label="Fechar análise por IA" onClick={() => setAiInsight(null)}>
              <X size={16} />
            </button>
          </div>
          <div className="ai-insight-body">{aiInsight.text}</div>
        </section>
      )}
      <section className="summary-strip">
        <div>
          <WalletCards size={20} />
          <span>Economia nesta página</span>
          <strong>{usd(totalSavings)}/mês</strong>
        </div>
        <div><span>Resultados</span><strong>{loading ? "…" : total}</strong></div>
      </section>
      <section className="panel table-panel" aria-busy={loading || saving}>
        <div className="toolbar opportunities-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              disabled={saving}
              aria-label="Buscar recurso ou oportunidade"
              placeholder="Buscar recurso ou oportunidade"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label className="select-field">
            <Building2 size={16} />
            <select
              disabled={saving}
              aria-label="Filtrar por conta"
              value={accountId}
              onChange={(event) => changeFilter("account_id", event.target.value)}
            >
              <option value="all">Todas as contas</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.aws_account_id}>
                  {account.name} · {account.aws_account_id}
                </option>
              ))}
            </select>
          </label>
          <label className="select-field">
            <Filter size={16} />
            <select
              disabled={saving}
              aria-label="Filtrar por prioridade"
              value={severity}
              onChange={(event) => changeFilter("severity", event.target.value)}
            >
              <option value="all">Todas as prioridades</option>
              <option value="high">Alta</option>
              <option value="medium">Média</option>
              <option value="low">Baixa</option>
            </select>
          </label>
          <label className="select-field">
            <select
              disabled={saving}
              aria-label="Filtrar por status"
              value={status}
              onChange={(event) => changeFilter("status", event.target.value)}
            >
              <option value="open">Abertas</option>
              <option value="treated">Tratadas</option>
              <option value="rejected">Rejeitadas</option>
            </select>
          </label>
          <label className="select-field">
            <Tags size={16} />
            <select
              disabled={saving}
              aria-label="Filtrar por tipo de oportunidade"
              value={ruleKey}
              onChange={(event) => changeFilter("rule_key", event.target.value)}
            >
              <option value="all">Todos os tipos</option>
              {ruleOptions.map(([key, name]) => (
                <option key={key} value={key}>{name}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="bulk-toolbar">
          <label className="selection-control">
            <input
              ref={selectAllRef}
              type="checkbox"
              checked={allSelected}
              disabled={loading || saving || !findings.length}
              onChange={() =>
                setSelectedIds(
                  allSelected ? new Set() : new Set(findings.map((finding) => finding.id)),
                )
              }
            />
            Selecionar esta página ({findings.length})
          </label>
          <span role="status">{selected.length} selecionada(s)</span>
          <div className="bulk-actions">
            <button
              className="button ghost"
              disabled={saving || !selected.length}
              onClick={() => setSelectedIds(new Set())}
            >
              Limpar seleção
            </button>
            {status === "open" ? (
              <>
                <button
                  className="button ghost"
                  disabled={saving || !selected.length}
                  onClick={() => void lifecycle(selected.map((item) => item.id), "treat")}
                >
                  Marcar como tratadas
                </button>
                <button
                  className="button primary"
                  disabled={saving || !selected.length}
                  onClick={() => void lifecycle(selected.map((item) => item.id), "reject")}
                >
                  {saving ? "Aplicando…" : "Rejeitar selecionadas"}
                </button>
              </>
            ) : (
              <button
                className="button primary"
                disabled={saving || !selected.length}
                onClick={() => void lifecycle(selected.map((item) => item.id), "reopen")}
              >
                Reabrir selecionadas
              </button>
            )}
          </div>
        </div>
        <div
          className="data-table-wrap"
          role="region"
          aria-label="Oportunidades encontradas"
          tabIndex={0}
        >
          <table className="data-table opportunities-table" aria-label="Oportunidades de economia">
            <thead>
              <tr>
                <th scope="col" className="selection-cell">Seleção</th>
                <th scope="col">Oportunidade</th>
                <th scope="col">Conta / Região</th>
                <th scope="col">Prioridade</th>
                <th scope="col">Economia</th>
                <th scope="col">Última validação</th>
                <th scope="col">Ações</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((finding) => (
                <Fragment key={finding.id}>
                  <tr className={selectedIds.has(finding.id) ? "selected-row" : undefined}>
                    <td className="selection-cell">
                      <label className="selection-control">
                        <input
                          type="checkbox"
                          aria-label={`Selecionar ${finding.title} · ${finding.resource_id}`}
                          checked={selectedIds.has(finding.id)}
                          disabled={saving}
                          onChange={() => toggleSelection(finding.id)}
                        />
                      </label>
                    </td>
                    <td>
                      <strong>{finding.title}</strong>
                      <span>{finding.resource_name || finding.resource_id}</span>
                      <p className="finding-reason">{findingExplanation(finding).summary}</p>
                      <button
                        className="evidence-toggle"
                        aria-expanded={expandedIds.has(finding.id)}
                        aria-controls={`evidence-${finding.id}`}
                        onClick={() =>
                          setExpandedIds((current) => {
                            const next = new Set(current);
                            if (next.has(finding.id)) next.delete(finding.id);
                            else next.add(finding.id);
                            return next;
                          })
                        }
                      >
                        {expandedIds.has(finding.id) ? "Ocultar evidências" : "Ver evidências"}
                      </button>
                    </td>
                    <td>
                      <strong>{finding.account_name}</strong>
                      <span>{finding.region} · {finding.service}</span>
                    </td>
                    <td><StatusBadge value={finding.severity} /></td>
                    <td className="money-cell">
                      {finding.rule_key === "cost_growth_anomaly" ? (
                        <span>Não estimada</span>
                      ) : (
                        <>{usd(finding.estimated_monthly_savings)}<span>/mês</span></>
                      )}
                    </td>
                    <td className="date-cell">{formatDate(finding.last_seen_at)}</td>
                    <td>
                      <div className="row-actions">
                        <StatusBadge value={finding.status} />
                        {finding.needs_review && <span>Detectada novamente</span>}
                        <button
                          onClick={() => void explain(finding)}
                          disabled={saving || aiLoading !== null}
                        >
                          {aiLoading === finding.id ? "Analisando…" : "Analisar IA"}
                        </button>
                        {finding.status === "open" ? (
                          <>
                            <button
                              disabled={saving}
                              onClick={() => void lifecycle([finding.id], "treat")}
                            >
                              Marcar como tratado
                            </button>
                            <button
                              disabled={saving}
                              onClick={() => void lifecycle([finding.id], "reject")}
                            >
                              Rejeitar
                            </button>
                          </>
                        ) : (
                          <button
                            disabled={saving}
                            onClick={() => void lifecycle([finding.id], "reopen")}
                          >
                            Reabrir
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedIds.has(finding.id) && (
                    <tr className="evidence-row" id={`evidence-${finding.id}`}>
                      <td colSpan={7}><FindingEvidence finding={finding} /></td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {loading ? (
            <div className="empty-table" role="status">Carregando oportunidades…</div>
          ) : !findings.length ? (
            <div className="empty-table">
              {error
                ? "Não foi possível carregar as oportunidades. Recarregue a página para tentar novamente."
                : "Nenhuma oportunidade corresponde aos filtros."}
            </div>
          ) : null}
        </div>
        <div className="bulk-toolbar">
          <span>
            Página {totalPages ? page : 0} de {totalPages} · {total} resultado(s)
          </span>
          <div className="bulk-actions">
            <button
              className="button ghost"
              disabled={loading || page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Anterior
            </button>
            <button
              className="button ghost"
              disabled={loading || page >= totalPages}
              onClick={() => setPage((current) => current + 1)}
            >
              Próxima
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
