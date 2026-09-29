"use client";

import Link from "next/link";

import { useEffect, useMemo, useRef, useState } from "react";
import { BrainCircuit, Clock3, Copy, History, RotateCcw, X } from "lucide-react";
import { FindingEvidence } from "@/components/finding-evidence";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate } from "@/lib/api";
import { formatAccountLabel, formatMoney, providerLabel } from "@/lib/cloud.mjs";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import type {
  OpportunityDetail as OpportunityDetailType,
  OpportunityObservation,
  OpportunityObservationPage,
  OpportunityStatusHistoryPage,
} from "@/lib/types";
import type { OpportunityDecisionAction } from "@/components/opportunity-decision-dialog";

const rejectionReasonLabels: Record<string, string> = {
  FALSE_POSITIVE: "Falso positivo",
  OPERATIONAL_EXCEPTION: "Exceção operacional",
  ACCEPTABLE_COST: "Custo aceitável",
  RESOURCE_REQUIRED: "Recurso necessário",
  RISK_ACCEPTED: "Risco aceito",
  OTHER: "Outro",
};

function monthlySavings(item: OpportunityDetailType) {
  return item.rule_key === "cost_growth_anomaly"
    ? "Não estimada"
    : `${formatMoney(item.estimated_monthly_savings, item.currency)}/mês`;
}

type Props = {
  opportunityId: string;
  onClose: () => void;
  onAction: (action: OpportunityDecisionAction, id: string) => void;
};

export function OpportunityDetail({ opportunityId, onClose, onAction }: Props) {
  const [selectedObservation, setSelectedObservation] = useState<OpportunityObservation | null>(null);
  const [actionError, setActionError] = useState("");
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [aiInsight, setAiInsight] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const historyPageSize = historyExpanded ? 50 : 8;
  const detailRequest = useApiQuery<OpportunityDetailType>({
    key: queryKeys.opportunities.detail(opportunityId),
    path: `/opportunities/${opportunityId}`,
    ...cachePolicy.detail,
  });
  const observationRequest = useApiQuery<OpportunityObservationPage>({
    key: queryKeys.opportunities.history(
      opportunityId,
      historyPage,
      historyPageSize,
    ),
    path: `/opportunities/${opportunityId}/history?page=${historyPage}&page_size=${historyPageSize}`,
    ...cachePolicy.detail,
    keepPreviousData: true,
    placeholderIdentity: `${opportunityId}:${historyPageSize}`,
  });
  const decisionRequest = useApiQuery<OpportunityStatusHistoryPage>({
    key: queryKeys.opportunities.statusHistory(opportunityId),
    path: `/opportunities/${opportunityId}/status-history?page=1&page_size=50`,
    ...cachePolicy.detail,
  });

  const detail = detailRequest.data ?? null;
  const observations = observationRequest.data ?? null;
  const decisions = decisionRequest.data ?? null;
  const loading = detailRequest.isLoading;
  const detailError = detailRequest.error?.message || "";
  const observationError = observationRequest.error
    ? "O detalhe foi carregado, mas o histórico de detecção está temporariamente indisponível."
    : "";
  const decisionError = decisionRequest.error
    ? "O detalhe foi carregado, mas o histórico de decisões está temporariamente indisponível."
    : "";
  const error =
    actionError || detailError || observationError || decisionError;

  useEffect(() => {
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  useEffect(() => {
    setSelectedObservation(null);
  }, [opportunityId]);

  const currentDecision = useMemo(() => {
    if (!detail || !decisions) return null;
    return decisions.items.find((item) => item.to_status === detail.status) || null;
  }, [decisions, detail]);

  async function explain() {
    if (!detail || aiLoading) return;
    setAiLoading(true);
    setAiInsight("");
    setActionError("");
    try {
      const result = await api<{ explanation: string }>(`/findings/${detail.id}/explain`, { method: "POST" });
      setAiInsight(result.explanation);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Falha na análise por IA");
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <aside className="opportunity-drawer" role="dialog" aria-modal="true" aria-labelledby="opportunity-detail-title">
        <header className="drawer-heading">
          <div>
            <span className="eyebrow">DETALHE DA OPORTUNIDADE</span>
            <h2 id="opportunity-detail-title">{detail?.title || "Carregando oportunidade…"}</h2>
            {detail && <p>{detail.resource_name || detail.resource_id}</p>}
          </div>
          <button ref={closeRef} className="icon-button" type="button" aria-label="Fechar detalhe" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        {error && <div className="alert error" role="alert">{error}</div>}
        {loading && !detail ? (
          <div className="drawer-loading" role="status">Carregando contexto e histórico…</div>
        ) : detail ? (
          <div className="drawer-content">
            <section className="detail-overview" aria-label="Resumo da oportunidade">
              <div className="detail-status-line">
                <StatusBadge value={detail.status} />
                <StatusBadge value={detail.severity} />
                {detail.needs_review && <span className="review-flag">Detectada novamente após tratamento</span>}
              </div>
              <p className="detail-description">{detail.description}</p>
              <dl className="detail-grid">
                <div><dt>Cloud</dt><dd>{providerLabel(detail.provider)}</dd></div>
                <div><dt>Conta</dt><dd>{formatAccountLabel(detail.account_name, detail.account_id)}</dd></div>
                <div><dt>Região</dt><dd>{detail.region || "—"}</dd></div>
                <div><dt>Serviço</dt><dd>{detail.service || "—"}</dd></div>
                <div><dt>Recurso</dt><dd>{detail.resource_id}</dd></div>
                {detail.resource_type && <div><dt>Tipo de recurso</dt><dd>{detail.resource_type}</dd></div>}
                <div>
                  <dt>Regra</dt>
                  <dd>
                    {detail.rule.name}
                    <span>{detail.rule.description}</span>
                  </dd>
                </div>
                <div><dt>Economia potencial</dt><dd className="detail-money">{monthlySavings(detail)}</dd></div>
                <div><dt>Custo mensal atual</dt><dd>{formatMoney(detail.current_monthly_cost, detail.currency)}</dd></div>
                <div><dt>Primeira detecção</dt><dd>{formatDate(detail.first_seen_at)}</dd></div>
                <div><dt>Última detecção</dt><dd>{formatDate(detail.last_seen_at)}</dd></div>
                <div><dt>Ocorrências históricas</dt><dd>{detail.total_occurrence_count}</dd></div>
                <div><dt>Detalhes retidos</dt><dd>{observations?.retained_total ?? "—"}</dd></div>
                <div><dt>Confiança</dt><dd>{detail.confidence || "—"}</dd></div>
              </dl>
            </section>

            {(detail.status === "treated" || detail.status === "rejected") && (
              <section className="detail-section decision-summary" aria-labelledby="decision-summary-title">
                <div className="section-heading-inline">
                  <h3 id="decision-summary-title">Decisão atual</h3>
                  <StatusBadge value={detail.status} />
                </div>
                <dl className="decision-grid">
                  <div><dt>Decidido por</dt><dd>{currentDecision?.changed_by_name || "Não registrado"}</dd></div>
                  <div><dt>Data</dt><dd>{formatDate(currentDecision?.changed_at ?? (detail.status === "treated" ? detail.treated_at : detail.rejected_at) ?? null)}</dd></div>
                  {detail.status === "rejected" && <div><dt>Motivo</dt><dd>{rejectionReasonLabels[detail.rejection_reason || ""] || detail.rejection_reason || "Não registrado"}</dd></div>}
                  <div className="decision-note"><dt>Observação</dt><dd>{currentDecision?.note || (detail.status === "treated" ? detail.treatment_note : detail.rejection_note) || "Sem observação registrada."}</dd></div>
                </dl>
              </section>
            )}

            <section className="detail-section evidence-section">
              {selectedObservation && (
                <div className="historical-evidence-banner">
                  <div>
                    <strong>Evidência histórica</strong>
                    <span>
                      Exibindo a coleta de {formatDate(selectedObservation.observed_at)}.
                    </span>
                  </div>
                  <button
                    className="button ghost"
                    type="button"
                    onClick={() => setSelectedObservation(null)}
                  >
                    Voltar à evidência mais recente
                  </button>
                </div>
              )}
              <FindingEvidence
                evidence={selectedObservation?.evidence ?? detail.latest_evidence}
                observedAt={
                  selectedObservation?.observed_at ??
                  detail.latest_observation?.observed_at ??
                  detail.last_seen_at
                }
                collectionRunId={
                  selectedObservation?.collection_run_id ??
                  detail.latest_observation?.collection_run_id ??
                  null
                }
              />
              <div className="ai-detail-action">
                <button className="button ghost" type="button" disabled={aiLoading} onClick={() => void explain()}>
                  <BrainCircuit size={17} /> {aiLoading ? "Analisando…" : "Aprofundar com IA"}
                </button>
              </div>
              {aiInsight && <div className="ai-insight-body ai-detail-result">{aiInsight}</div>}
            </section>

            <section className="detail-section" aria-labelledby="detection-history-title">
              <div className="section-heading-inline">
                <div>
                  <h3 id="detection-history-title"><Clock3 size={18} /> Histórico de detecção</h3>
                  <p>Observações factuais registradas pelas coletas. A mais recente aparece primeiro.</p>
                </div>
                {observations && (
                  <span>
                    {observations.retained_total} detalhe(s) retido(s) de{" "}
                    {observations.total_occurrence_count} ocorrência(s)
                  </span>
                )}
              </div>
              {observations && !observations.history_complete && (
                <div className="alert" role="status">
                  <strong>Histórico detalhado parcialmente expirado.</strong>
                  <p>
                    A configuração atual retém observações por {observations.retention_days} dias.
                    Evidências intermediárias fora dessa janela podem ter sido removidas; primeira
                    e última detecção, identidade da oportunidade e decisões humanas permanecem
                    preservadas.
                  </p>
                </div>
              )}
              {observations?.items.length ? (
                <div className="history-list">
                  {observations.items.map((item) => (
                    <article
                      key={item.id}
                      className={`history-item${selectedObservation?.id === item.id ? " selected" : ""}`}
                    >
                      <div>
                        <strong>{formatDate(item.observed_at)}</strong>
                        <span>{providerLabel(item.collection_provider)} · {item.collection_account_id}</span>
                      </div>
                      <div><StatusBadge value={item.severity} /></div>
                      <div>
                        <strong>{formatMoney(item.estimated_monthly_savings, item.currency)}/mês</strong>
                        <span>economia estimada</span>
                      </div>
                      <div>
                        <span>Coleta <StatusBadge value={item.collection_status} /></span>
                        <Link className="collection-link" href={`/collections/${encodeURIComponent(item.collection_run_id)}`}>Abrir coleta {item.collection_run_id.slice(0, 8)}</Link>
                      </div>
                      <p className="history-evidence-summary">{item.evidence.summary}</p>
                      <button
                        className="button ghost history-evidence-button"
                        type="button"
                        onClick={() => setSelectedObservation(item)}
                      >
                        Ver evidência desta coleta
                      </button>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">
                  {observations && !observations.history_complete
                    ? "Nenhuma observação detalhada permanece na janela atualmente retida."
                    : "Nenhuma observação histórica disponível."}
                </p>
              )}
              {observations && !historyExpanded && observations.retained_total > 8 && (
                <button className="button ghost history-more" type="button" onClick={() => { setHistoryPage(1); setHistoryExpanded(true); }}>Ver histórico completo</button>
              )}
              {observations && historyExpanded && observations.total_pages > 1 && (
                <div className="history-pagination" aria-label="Paginação do histórico de detecção">
                  <button className="button ghost" type="button" disabled={historyPage <= 1} onClick={() => setHistoryPage((page) => Math.max(1, page - 1))}>Anterior</button>
                  <span>Página {observations.page} de {observations.total_pages}</span>
                  <button className="button ghost" type="button" disabled={historyPage >= observations.total_pages} onClick={() => setHistoryPage((page) => page + 1)}>Próxima</button>
                </div>
              )}
            </section>

            <section className="detail-section" aria-labelledby="decision-history-title">
              <div className="section-heading-inline">
                <div>
                  <h3 id="decision-history-title"><History size={18} /> Histórico de decisões</h3>
                  <p>Transições manuais de estado, separadas das detecções técnicas.</p>
                </div>
                {decisions && <span>{decisions.total} decisão(ões)</span>}
              </div>
              {decisions?.items.length ? (
                <div className="decision-history">
                  {decisions.items.map((item) => (
                    <article key={item.id}>
                      <div className="decision-marker" />
                      <div>
                        <strong>{formatDate(item.changed_at)} · {item.changed_by_name || "Usuário não registrado"}</strong>
                        <p><StatusBadge value={item.from_status} /> <span aria-hidden="true">→</span> <StatusBadge value={item.to_status} /></p>
                        {item.reason && <span>Motivo: {rejectionReasonLabels[item.reason] || item.reason}</span>}
                        {item.note && <blockquote>{item.note}</blockquote>}
                      </div>
                    </article>
                  ))}
                </div>
              ) : <p className="muted-copy">Nenhuma decisão manual registrada.</p>}
            </section>

            <details className="technical-details">
              <summary>Informações técnicas</summary>
              <dl>
                <div><dt>ID da oportunidade</dt><dd className="technical-copy"><code>{detail.id}</code><button type="button" className="copy-inline" title="Copiar ID da oportunidade" aria-label="Copiar ID da oportunidade" onClick={() => void navigator.clipboard.writeText(detail.id)}><Copy size={14} /></button></dd></div>
                <div><dt>Fingerprint</dt><dd className="technical-copy"><code>{detail.fingerprint}</code><button type="button" className="copy-inline" title="Copiar fingerprint" aria-label="Copiar fingerprint" onClick={() => void navigator.clipboard.writeText(detail.fingerprint)}><Copy size={14} /></button></dd></div>
                <div><dt>Regra técnica</dt><dd><code>{detail.rule.key}</code></dd></div>
                <div><dt>Scan legado</dt><dd><code>{detail.scan_id || "—"}</code></dd></div>
                {Object.keys(detail.provider_metadata || {}).length > 0 && (
                  <div><dt>Metadata do provider</dt><dd><pre>{JSON.stringify(detail.provider_metadata, null, 2)}</pre></dd></div>
                )}
              </dl>
            </details>
          </div>
        ) : null}

        {detail && (
          <footer className="drawer-actions">
            {detail.status === "open" ? (
              <>
                <button className="button ghost" type="button" onClick={() => onAction("treat", detail.id)}>Marcar como tratada</button>
                <button className="button primary" type="button" onClick={() => onAction("reject", detail.id)}>Rejeitar</button>
              </>
            ) : (
              <button className="button primary" type="button" onClick={() => onAction("reopen", detail.id)}><RotateCcw size={17} /> Reabrir</button>
            )}
          </footer>
        )}
      </aside>
    </div>
  );
}
