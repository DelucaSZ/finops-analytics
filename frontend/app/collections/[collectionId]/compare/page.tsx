"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, GitCompareArrows } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge, statusLabel } from "@/components/status-badge";
import { ApiError, formatDate } from "@/lib/api";
import { formatMoney, providerLabel } from "@/lib/cloud.mjs";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { prefetchApiQuery, useApiQuery } from "@/lib/server-state";
import type {
  CollectionComparisonCategory,
  CollectionComparisonChange,
  CollectionComparisonResponse,
  CollectionComparisonRun,
} from "@/lib/types";
import styles from "../../collection.module.css";

const categories: Array<{
  value: CollectionComparisonCategory;
  label: string;
  summaryKey: "new" | "persistent" | "no_longer_detected" | "changed";
}> = [
  { value: "NEW", label: "Novas", summaryKey: "new" },
  { value: "PERSISTENT", label: "Persistentes", summaryKey: "persistent" },
  {
    value: "NO_LONGER_DETECTED",
    label: "Não detectadas",
    summaryKey: "no_longer_detected",
  },
  { value: "CHANGED", label: "Alteradas", summaryKey: "changed" },
];

const categoryValues = new Set(categories.map((item) => item.value));

function signedMoney(value: number | string, currency: string) {
  const number = Number(value);
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatMoney(number, currency)}/mês`;
}

function displayValue(value: unknown, unit?: string | null): string {
  if (value === null || value === undefined) return "—";
  const currencyUnit = unit?.match(/^([A-Z]{3})_MONTH$/);
  if (currencyUnit && (typeof value === "number" || typeof value === "string")) {
    return `${formatMoney(value, currencyUnit[1])}/mês`;
  }
  if (typeof value === "number") {
    const rendered = value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
    return unit ? `${rendered} ${unit}` : rendered;
  }
  if (typeof value === "string" || typeof value === "boolean") {
    return `${String(value)}${unit ? ` ${unit}` : ""}`;
  }
  if (Array.isArray(value)) {
    const primitives = value.filter(
      (item) => ["string", "number", "boolean"].includes(typeof item),
    );
    return primitives.length === value.length
      ? primitives.join(", ")
      : `${value.length} item(ns) estruturado(s)`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("threshold_value" in record) {
      return [record.operator, record.threshold_value, record.unit]
        .filter((item) => item !== null && item !== undefined && item !== "")
        .join(" ");
    }
    const entries = Object.entries(record).slice(0, 4);
    if (!entries.length) return "Sem valores";
    return entries
      .map(([key, item]) => {
        const simple =
          item === null || ["string", "number", "boolean"].includes(typeof item)
            ? String(item ?? "—")
            : "estrutura alterada";
        return `${key}: ${simple}`;
      })
      .join(" · ");
  }
  return String(value);
}

function changeLabel(change: CollectionComparisonChange) {
  if (change.type === "severity") return "Severidade";
  if (change.type === "financial_impact") return change.label;
  if (change.type === "threshold") return `Threshold · ${change.label}`;
  if (change.type === "parameters") return "Parâmetros da regra";
  if (change.type === "confidence") return "Confiança";
  return change.label;
}

export default function CollectionComparisonPage() {
  return (
    <Suspense fallback={<div className={styles.state}>Comparando coletas…</div>}>
      <CollectionComparisonContent />
    </Suspense>
  );
}

function CollectionComparisonContent() {
  const params = useParams<{ collectionId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const collectionId = params.collectionId;
  const searchKey = searchParams.toString();

  const category = useMemo<CollectionComparisonCategory>(() => {
    const requested = searchParams.get("category") as CollectionComparisonCategory | null;
    return requested && categoryValues.has(requested) ? requested : "NEW";
  }, [searchKey, searchParams]);
  const page = useMemo(() => {
    const requested = Number.parseInt(searchParams.get("page") || "1", 10);
    return Number.isInteger(requested) && requested > 0 ? requested : 1;
  }, [searchKey, searchParams]);
  const baselineId = searchParams.get("baseline_id") || "";

  const comparisonQuery = useMemo(() => {
    const query = new URLSearchParams({
      category,
      page: String(page),
      page_size: "50",
    });
    if (baselineId) query.set("baseline_id", baselineId);
    return query.toString();
  }, [baselineId, category, page]);

  const comparisonRequest = useApiQuery<CollectionComparisonResponse>({
    key: queryKeys.collections.comparison(
      collectionId,
      baselineId,
      category,
      page,
      50,
    ),
    path: `/collections/${collectionId}/compare?${comparisonQuery}`,
    ...cachePolicy.comparison,
    keepPreviousData: true,
    placeholderIdentity: `${collectionId}:${baselineId}:${category}`,
  });
  const optionsRequest = useApiQuery<CollectionComparisonRun[]>({
    key: queryKeys.collections.comparisonOptions(collectionId),
    path: `/collections/${collectionId}/comparison-options?limit=100`,
    ...cachePolicy.metadata,
  });

  const comparison = comparisonRequest.data ?? null;
  const options = optionsRequest.data ?? [];
  const loading = comparisonRequest.isLoading;
  const error = comparisonRequest.error
    ? comparisonRequest.error instanceof ApiError && comparisonRequest.error.status === 404
      ? "Coleta não encontrada."
      : comparisonRequest.error instanceof ApiError && comparisonRequest.error.status === 410
        ? "A comparação detalhada não está mais disponível pela política de retenção."
        : comparisonRequest.error.message
    : "";

  const updateUrl = useCallback(
    (patch: Record<string, string | number | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      router.push(`/collections/${collectionId}/compare?${next.toString()}`);
    },
    [collectionId, router, searchParams],
  );

  useEffect(() => {
    if (baselineId || !comparison?.baseline?.id) return;
    const next = new URLSearchParams(searchParams.toString());
    next.set("baseline_id", comparison.baseline.id);
    next.set("category", category);
    next.set("page", String(page));
    router.replace(`/collections/${collectionId}/compare?${next.toString()}`);
  }, [
    baselineId,
    category,
    collectionId,
    comparison?.baseline?.id,
    page,
    router,
    searchParams,
  ]);

  useEffect(() => {
    if (!comparison || comparison.page >= comparison.total_pages) return;
    const nextPage = comparison.page + 1;
    const query = new URLSearchParams({
      category,
      page: String(nextPage),
      page_size: "50",
    });
    if (baselineId) query.set("baseline_id", baselineId);
    void prefetchApiQuery<CollectionComparisonResponse>({
      key: queryKeys.collections.comparison(
        collectionId,
        baselineId,
        category,
        nextPage,
        50,
      ),
      path: `/collections/${collectionId}/compare?${query.toString()}`,
      ...cachePolicy.comparison,
    }).catch(() => undefined);
  }, [
    baselineId,
    category,
    collectionId,
    comparison,
  ]);

  if (loading && !comparison) {
    return <div className={styles.state}>Comparando coletas…</div>;
  }

  if (error && !comparison) {
    return (
      <div className={styles.state} role="alert">
        {error}
      </div>
    );
  }

  if (!comparison) return null;

  const selectedBaseline = comparison.baseline;
  const summary = comparison.summary;
  const selectedCategory = categories.find((item) => item.value === category) ?? categories[0];
  const financial = comparison.financial_summary;
  const comparisonReturnParams = new URLSearchParams({
    category,
    page: String(page),
  });
  if (selectedBaseline) comparisonReturnParams.set("baseline_id", selectedBaseline.id);
  const comparisonReturnTo = `/collections/${encodeURIComponent(collectionId)}/compare?${comparisonReturnParams.toString()}`;
  const unavailableMessage =
    comparison.reason === "OBSERVATIONS_EXPIRED"
      ? "A comparação detalhada está indisponível porque as observações históricas de uma das coletas expiraram pela política de retenção. Os resumos das coletas e o histórico de decisões permanecem preservados."
      : comparison.message ||
        "Não existe uma coleta anterior compatível disponível para comparação.";

  return (
    <>
      <PageHeader
        eyebrow="COMPARAÇÃO TEMPORAL"
        title="Comparação de coletas"
        description="Diff técnico entre duas execuções equivalentes, independente das decisões humanas sobre as oportunidades."
        actions={
          <div className={styles.headerActions}>
            <Link className="button ghost" href={`/collections/${comparison.target.id}`}>
              Abrir coleta atual
            </Link>
            <Link className="button ghost" href="/collections">
              Ver todas as coletas
            </Link>
          </div>
        }
      />

      {error && <div className="alert error">{error}</div>}
      {optionsRequest.error && comparison && (
        <div className="alert">
          A comparação foi carregada, mas as opções de baseline não puderam ser atualizadas.
        </div>
      )}
      {comparisonRequest.isFetching && comparison && (
        <div className="table-loading-bar" role="status">
          <span /> Atualizando comparação…
        </div>
      )}

      <section className={`panel ${styles.compareHeader}`}>
        <div className={styles.runSide}>
          <span className="eyebrow">COLETA BASE</span>
          {selectedBaseline ? (
            <>
              <Link href={`/collections/${selectedBaseline.id}`}>
                {formatDate(selectedBaseline.started_at)}
              </Link>
              <strong>
                {providerLabel(selectedBaseline.provider)} · {selectedBaseline.account_id}
              </strong>
              <span>Regras {selectedBaseline.rules_version || "não registrada"}</span>
            </>
          ) : (
            <strong>Sem baseline disponível</strong>
          )}
        </div>
        <GitCompareArrows size={25} />
        <div className={styles.runSide}>
          <span className="eyebrow">COLETA ALVO</span>
          <Link href={`/collections/${comparison.target.id}`}>
            {formatDate(comparison.target.started_at)}
          </Link>
          <strong>
            {providerLabel(comparison.target.provider)} · {comparison.target.account_id}
          </strong>
          <span>Regras {comparison.target.rules_version || "não registrada"}</span>
        </div>
        <label className={styles.baselinePicker}>
          Comparar com
          <select
            value={selectedBaseline?.id || ""}
            disabled={!options.length}
            onChange={(event) =>
              updateUrl({ baseline_id: event.target.value || null, page: 1 })
            }
          >
            {!options.length && <option value="">Nenhuma coleta compatível</option>}
            {options.map((option) => (
              <option value={option.id} key={option.id}>
                {formatDate(option.started_at)} · {statusLabel(option.status)} · Regras{" "}
                {option.rules_version || "n/d"}
                {!option.detailed_observations_available ? " · detalhe expirado" : ""}
              </option>
            ))}
          </select>
        </label>
      </section>

      {!comparison.available && (
        <div className={`alert ${styles.notice}`}>
          {unavailableMessage}
        </div>
      )}

      {comparison.rules_version_warning && (
        <div className={`alert ${styles.notice}`}>
          <strong>Contexto de rules version:</strong>{" "}
          {comparison.rules_version_warning.message}
        </div>
      )}

      {comparison.warnings.map((warning) => (
        <div className={`alert ${styles.notice}`} key={warning.code}>
          <strong>{warning.code === "SCOPE_METADATA_UNAVAILABLE" ? "Escopo:" : "Aviso:"}</strong>{" "}
          {warning.message}
        </div>
      ))}

      {summary && (
        <section className={styles.summaryCards} aria-label="Resumo da comparação">
          {categories.map((item) => (
            <button
              type="button"
              key={item.value}
              className={`${styles.summaryCard} ${
                category === item.value ? styles.summaryCardActive : ""
              }`}
              onClick={() => updateUrl({ category: item.value, page: 1 })}
            >
              <span>{item.label}</span>
              <strong>{summary[item.summaryKey]}</strong>
            </button>
          ))}
        </section>
      )}

      {financial && (
        <section className={styles.financialGrid}>
          <article>
            <span>Impacto anterior</span>
            <strong>{formatMoney(financial.baseline_total, financial.currency)}/mês</strong>
          </article>
          <article>
            <span>Impacto atual</span>
            <strong>{formatMoney(financial.target_total, financial.currency)}/mês</strong>
          </article>
          <article>
            <span>Variação</span>
            <strong>{signedMoney(financial.delta, financial.currency)}</strong>
            {financial.delta_percent !== null && (
              <small>
                {Number(financial.delta_percent) > 0 ? "+" : ""}
                {Number(financial.delta_percent).toLocaleString("pt-BR", {
                  maximumFractionDigits: 1,
                })}
                %
              </small>
            )}
          </article>
          <p>
            Métrica: {financial.label}. O resumo agrega apenas{" "}
            <code>{financial.metric}</code> em {financial.currency}/mês.
          </p>
        </section>
      )}

      {comparison.available && summary && (
        <section className={`panel table-panel ${styles.resultsPanel}`}>
          <div className="panel-heading">
            <div>
              <span className="eyebrow">DETALHE PAGINADO</span>
              <h2>{selectedCategory.label}</h2>
              <p>
                {comparison.total} oportunidade(s) nesta categoria · página{" "}
                {comparison.total_pages ? comparison.page : 0} de {comparison.total_pages}
              </p>
            </div>
          </div>

          <div className="data-table-wrap" role="region" aria-label={selectedCategory.label}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Oportunidade</th>
                  <th scope="col">Contexto</th>
                  <th scope="col">Baseline</th>
                  <th scope="col">Atual</th>
                  <th scope="col">Lifecycle</th>
                  <th scope="col">Mudanças</th>
                  <th scope="col">Ação</th>
                </tr>
              </thead>
              <tbody>
                {comparison.items.map((item) => (
                  <tr key={item.opportunity_id}>
                    <td>
                      <strong>{item.title}</strong>
                      <span>{item.rule_key}</span>
                      <span>{item.resource_name || item.resource_id}</span>
                    </td>
                    <td>
                      <strong>
                        {item.service} · {item.region || "Sem região"}
                      </strong>
                      <span>{item.resource_id}</span>
                      {item.resource_type && <span>{item.resource_type}</span>}
                    </td>
                    <td>
                      {item.baseline ? (
                        <>
                          <StatusBadge value={item.baseline.severity} />
                          <span>{formatMoney(item.baseline.estimated_monthly_savings, item.baseline.currency)}/mês</span>
                          <span>{item.baseline.evidence_summary || "Sem resumo"}</span>
                        </>
                      ) : (
                        <span>Não observada</span>
                      )}
                    </td>
                    <td>
                      {item.target ? (
                        <>
                          <StatusBadge value={item.target.severity} />
                          <span>{formatMoney(item.target.estimated_monthly_savings, item.target.currency)}/mês</span>
                          <span>{item.target.evidence_summary || "Sem resumo"}</span>
                        </>
                      ) : (
                        <span>Não detectada na coleta atual</span>
                      )}
                    </td>
                    <td>
                      <StatusBadge value={item.lifecycle_status} />
                    </td>
                    <td>
                      {item.changes.length ? (
                        <div className={styles.changeList}>
                          {item.changes.map((change, index) => (
                            <div
                              className={styles.change}
                              key={`${change.type}-${change.label}-${index}`}
                            >
                              <strong>{changeLabel(change)}</strong>
                              <span>
                                {change.type === "severity" || change.type === "confidence"
                                  ? statusLabel(String(change.baseline ?? ""))
                                  : displayValue(change.baseline, change.unit)}
                                <ArrowRight size={13} />
                                {change.type === "severity" || change.type === "confidence"
                                  ? statusLabel(String(change.target ?? ""))
                                  : displayValue(change.target, change.unit)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span>
                          {item.category === "PERSISTENT"
                            ? "Detectada em ambas as coletas"
                            : "Sem diff de atributos"}
                        </span>
                      )}
                    </td>
                    <td>
                      <Link
                        onMouseEnter={() => {
                          void prefetchApiQuery({
                            key: queryKeys.opportunities.detail(item.opportunity_id),
                            path: `/opportunities/${item.opportunity_id}`,
                            ...cachePolicy.detail,
                          }).catch(() => undefined);
                        }}
                        href={`/opportunities?opportunity_id=${encodeURIComponent(
                          item.opportunity_id,
                        )}&comparison_target=${encodeURIComponent(
                          comparison.target.id,
                        )}${
                          selectedBaseline
                            ? `&comparison_baseline=${encodeURIComponent(
                                selectedBaseline.id,
                              )}`
                            : ""
                        }&return_to=${encodeURIComponent(comparisonReturnTo)}`}
                      >
                        Abrir oportunidade
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {!comparison.items.length && (
              <div className="empty-table">
                Nenhuma oportunidade classificada como {selectedCategory.label.toLowerCase()}.
              </div>
            )}
          </div>

          <footer className={styles.pagination}>
            <button
              type="button"
              disabled={comparison.page <= 1}
              onClick={() => updateUrl({ page: comparison.page - 1 })}
            >
              <ChevronLeft size={16} />
              Anterior
            </button>
            <span>
              Página {comparison.total_pages ? comparison.page : 0} de{" "}
              {comparison.total_pages}
            </span>
            <button
              type="button"
              disabled={
                comparison.total_pages === 0 || comparison.page >= comparison.total_pages
              }
              onClick={() => updateUrl({ page: comparison.page + 1 })}
            >
              Próxima
              <ChevronRight size={16} />
            </button>
          </footer>
        </section>
      )}
    </>
  );
}
