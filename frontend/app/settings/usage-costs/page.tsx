"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { CloudAccount } from "@/lib/types";
import {
  USAGE_COST_PERIOD_PRESETS,
  buildUsageCostQuery,
  costItemsByCurrency,
  costShare,
  distinctUsageGroups,
  formatUsageCostDate,
  formatUsageCostMoney,
  formatUsageNumber,
  formatUsagePeriodLabel,
  friendlyUsageLabel,
  pricingVersionCount,
  resolveUsageCostPeriod,
  summarizeUsage,
  usageByGroup,
  usageCostGranularity,
} from "@/lib/deepops-usage-costs.mjs";
import styles from "./usage-costs.module.css";

const SHARED_ANALYZER = "__shared__";

type CostComponent = {
  pricing_rule_id: string;
  usage_quantity: string;
  unit_price: string;
  unit_quantity: string;
  pricing_unit: string;
  currency: string;
  effective_from: string;
  effective_until: string | null;
  source: string;
  source_reference: string;
  pricing_verified_at: string;
};

type CostItem = {
  group: string | null;
  period: string | null;
  currency: string;
  gross_estimated_cost: string;
  usage_quantity: string;
  priced_events: number;
  inexact_request_events: number;
  failed_events: number;
  components: CostComponent[];
};

type CostTotal = {
  currency: string;
  gross_estimated_cost: string;
  usage_quantity: string;
};

type UnpricedUsage = {
  operation: string;
  region: string;
  events: number;
  requests: number;
  reason: string;
};

type CostResponse = {
  group_by: string | null;
  granularity: string | null;
  items: CostItem[];
  totals: CostTotal[];
  priced_events: number;
  unpriced_events: number;
  unpriced_usage: UnpricedUsage[];
  is_complete: boolean;
  request_count_is_exact: boolean;
  inexact_request_events: number;
  failed_events: number;
  free_tier_applied: boolean;
  pricing_sources: string[];
  pricing_verified_at: string | null;
  estimation_basis: string;
};

type UsageSummaryItem = {
  group: string | null;
  events: number;
  requests: number;
  metric_queries: number;
  metrics_requested: number;
  failed_events: number;
};

type UsageSummary = {
  group_by: string;
  items: UsageSummaryItem[];
};

type CollectionItem = {
  id: string;
  provider: string;
  account_id: string;
  account_name: string | null;
  started_at: string;
  finished_at: string | null;
  status: string;
};

type CollectionPage = {
  items: CollectionItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type CostDashboard = {
  summary: CostResponse;
  timeseries: CostResponse;
  account: CostResponse;
  operation: CostResponse;
  collector: CostResponse;
  analyzer: CostResponse;
  collectionRun: CostResponse;
};

type UsageDashboard = {
  operation: UsageSummary;
  account: UsageSummary;
  collector: UsageSummary;
  analyzer: UsageSummary;
  collectionRun: UsageSummary;
};

type FilterOptions = {
  regions: string[];
  operations: string[];
  collectors: string[];
  analyzers: Array<{ value: string; label: string }>;
};

function message(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function accountLabel(account: CloudAccount) {
  return account.name
    ? `${account.name} · ${account.native_account_id}`
    : account.native_account_id;
}

function sourceLabel(source: string) {
  return source === "AWS_OFFICIAL_PRICING" ? "AWS CloudWatch Pricing" : source;
}

function CostTotals({ totals }: { totals: CostTotal[] }) {
  if (!totals.length) return <strong className={styles.unavailableValue}>Indisponível</strong>;
  return (
    <div className={styles.moneyStack}>
      {totals.map((total) => (
        <strong key={total.currency}>
          {formatUsageCostMoney(total.gross_estimated_cost, total.currency)}
        </strong>
      ))}
    </div>
  );
}

function CostChart({ response }: { response: CostResponse }) {
  const groups = costItemsByCurrency(response.items);
  if (!groups.length) {
    return <div className={styles.sectionState}>Não há custo precificado para plotar neste período.</div>;
  }

  const width = 920;
  const height = 270;
  const padX = 52;
  const padY = 32;

  return (
    <div className={styles.chartGroups}>
      {groups.map(([currency, items]) => {
        const points = [...items].sort((left, right) => String(left.period).localeCompare(String(right.period)));
        const values = points.map((point) => Number(point.gross_estimated_cost));
        const maximum = Math.max(0, ...values);
        const innerWidth = width - padX * 2;
        const innerHeight = height - padY * 2;
        const x = (index: number) => padX + (points.length === 1 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
        const y = (value: number) => padY + (maximum === 0 ? innerHeight : ((maximum - value) / maximum) * innerHeight);
        const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(Number(point.gross_estimated_cost))}`).join(" ");
        const first = points[0];
        const last = points[points.length - 1];
        return (
          <div className={styles.chartGroup} key={currency}>
            <div className={styles.chartMeta}>
              <strong>{currency}</strong>
              <span>{response.granularity === "monthly" ? "Buckets mensais" : "Buckets diários"}</span>
            </div>
            <div className={styles.chartScroll}>
              <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Custo estimado do DeepOps em ${currency} ao longo do tempo`}>
                <line x1={padX} x2={width - padX} y1={height - padY} y2={height - padY} className={styles.axisLine} />
                <path d={path} className={styles.costLine} />
                {points.map((point, index) => (
                  <circle key={`${point.period}-${currency}`} cx={x(index)} cy={y(Number(point.gross_estimated_cost))} r="4" className={styles.costPoint}>
                    <title>{`${point.period}: ${formatUsageCostMoney(point.gross_estimated_cost, currency)}`}</title>
                  </circle>
                ))}
                <text x={padX} y={height - 7} className={styles.axisLabel}>{first.period}</text>
                <text x={width - padX} y={height - 7} textAnchor="end" className={styles.axisLabel}>{last.period}</text>
              </svg>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BreakdownSection({
  title,
  subtitle,
  kind,
  cost,
  usage,
  accounts,
  showProvenance = false,
}: {
  title: string;
  subtitle: string;
  kind: "account" | "operation" | "collector" | "analyzer";
  cost: CostResponse;
  usage: UsageSummary;
  accounts: CloudAccount[];
  showProvenance?: boolean;
}) {
  const usageMap = usageByGroup(usage.items);
  const accountMap = new Map(accounts.map((account) => [account.native_account_id, account]));
  const groups = costItemsByCurrency(cost.items);

  const label = (value: string | null) => {
    if (kind === "account" && value) {
      const account = accountMap.get(value);
      return account ? accountLabel(account) : value;
    }
    return friendlyUsageLabel(value, kind);
  };

  const usageForCostGroup = (group: string | null) => {
    if (kind === "analyzer" && group === "Shared / Unattributed") return usageMap.get(null);
    return usageMap.get(group);
  };

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      {!groups.length ? (
        <div className={styles.sectionState}>Sem custo precificado para este recorte.</div>
      ) : (
        <div className={styles.panelBody}>
          {groups.map(([currency, rows]) => (
            <div className={styles.currencyGroup} key={currency}>
              <div className={styles.currencyHeading}><strong>{currency}</strong><span>Ordenado por custo estimado</span></div>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>{kind === "account" ? "Conta" : kind === "operation" ? "Operação" : kind === "collector" ? "Collector" : "Analyzer"}</th>
                      <th>Requests</th>
                      <th>Metric queries</th>
                      <th>Falhas</th>
                      <th>Custo estimado</th>
                      <th>% do custo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const technical = usageForCostGroup(row.group);
                      const share = costShare(row, rows);
                      return (
                        <tr key={`${currency}-${row.group ?? "none"}`}>
                          <td>
                            <strong>{label(row.group)}</strong>
                            {showProvenance && row.components.length > 0 && (
                              <details className={styles.provenance}>
                                <summary>Pricing aplicado</summary>
                                {row.components.map((component, index) => (
                                  <div key={`${component.pricing_rule_id}-${component.effective_from}-${index}`}>
                                    <span>Regra {component.pricing_rule_id}</span>
                                    <span>{formatUsageNumber(component.usage_quantity)} {component.pricing_unit}</span>
                                    <span>{formatUsageCostMoney(component.unit_price, component.currency)} / {formatUsageNumber(component.unit_quantity)} {component.pricing_unit}</span>
                                    <span>Vigência: {formatUsageCostDate(component.effective_from)}</span>
                                    <span>Fonte: {sourceLabel(component.source)}</span>
                                  </div>
                                ))}
                              </details>
                            )}
                          </td>
                          <td>{formatUsageNumber(technical?.requests ?? 0)}</td>
                          <td>{formatUsageNumber(technical?.metric_queries ?? 0)}</td>
                          <td>{formatUsageNumber(technical?.failed_events ?? row.failed_events)}</td>
                          <td><strong>{formatUsageCostMoney(row.gross_estimated_cost, currency)}</strong></td>
                          <td>{share === null ? "—" : `${share.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default function DeepOpsUsageCostsPage() {
  const [preset, setPreset] = useState("this-month");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [accountId, setAccountId] = useState("");
  const [region, setRegion] = useState("");
  const [operation, setOperation] = useState("");
  const [collector, setCollector] = useState("");
  const [analyzer, setAnalyzer] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [options, setOptions] = useState<FilterOptions>({ regions: [], operations: [], collectors: [], analyzers: [] });
  const [optionsError, setOptionsError] = useState("");

  const [cost, setCost] = useState<CostDashboard | null>(null);
  const [usage, setUsage] = useState<UsageDashboard | null>(null);
  const [collections, setCollections] = useState<CollectionItem[]>([]);
  const [costLoading, setCostLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(true);
  const [costError, setCostError] = useState("");
  const [usageError, setUsageError] = useState("");
  const [runsError, setRunsError] = useState("");
  const sequence = useRef(0);

  const period = useMemo(() => resolveUsageCostPeriod(preset, customStart, customEnd), [preset, customStart, customEnd]);
  const granularity = usageCostGranularity(period);
  const awsAccounts = useMemo(() => accounts.filter((account) => account.provider === "aws"), [accounts]);
  const selectedAccount = useMemo(() => awsAccounts.find((account) => String(account.id) === accountId) ?? null, [accountId, awsAccounts]);

  const canonicalFilters = useMemo(() => {
    if (!period) return null;
    return {
      date_from: period.date_from,
      date_to: period.date_to,
      cloud_account_id: accountId || undefined,
      region: region || undefined,
      operation: operation || undefined,
      collector: collector || undefined,
      analyzer: analyzer || undefined,
    };
  }, [period, accountId, region, operation, collector, analyzer]);

  useEffect(() => {
    const controller = new AbortController();
    api<CloudAccount[]>("/cloud-accounts", { signal: controller.signal })
      .then(setAccounts)
      .catch((error) => {
        if (!controller.signal.aborted) setOptionsError(message(error, "Falha ao carregar as contas AWS."));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!period) return;
    const controller = new AbortController();
    const periodQuery = { date_from: period.date_from, date_to: period.date_to };
    const summary = (groupBy: string) => api<UsageSummary>(`/usage/cloudwatch/summary${buildUsageCostQuery(periodQuery, { group_by: groupBy })}`, { signal: controller.signal });
    setOptionsError("");
    Promise.all([summary("region"), summary("operation"), summary("collector"), summary("analyzer")])
      .then(([regions, operations, collectors, analyzers]) => {
        if (controller.signal.aborted) return;
        const analyzerOptions = distinctUsageGroups(analyzers.items).map((value) => ({ value, label: friendlyUsageLabel(value, "analyzer") }));
        if (analyzers.items.some((item) => item.group === null)) {
          analyzerOptions.unshift({ value: SHARED_ANALYZER, label: "Compartilhado / não atribuído" });
        }
        setOptions({
          regions: distinctUsageGroups(regions.items),
          operations: distinctUsageGroups(operations.items),
          collectors: distinctUsageGroups(collectors.items),
          analyzers: analyzerOptions,
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setOptionsError(message(error, "Falha ao carregar opções da telemetria."));
      });
    return () => controller.abort();
  }, [period, refreshToken]);

  useEffect(() => {
    if (!canonicalFilters || !period) {
      setCost(null);
      setUsage(null);
      return;
    }
    const controller = new AbortController();
    const current = ++sequence.current;
    const signal = controller.signal;
    const costQuery = (suffix: string, extra: Record<string, string> = {}) => api<CostResponse>(`/deepops-costs/cloudwatch/${suffix}${buildUsageCostQuery(canonicalFilters, extra)}`, { signal });
    const usageQuery = (groupBy: string) => api<UsageSummary>(`/usage/cloudwatch/summary${buildUsageCostQuery(canonicalFilters, { group_by: groupBy })}`, { signal });

    setCostLoading(true);
    setUsageLoading(true);
    setRunsLoading(true);
    setCostError("");
    setUsageError("");
    setRunsError("");

    Promise.all([
      costQuery("summary"),
      costQuery("timeseries", { granularity }),
      costQuery("breakdown", { group_by: "account" }),
      costQuery("breakdown", { group_by: "operation" }),
      costQuery("breakdown", { group_by: "collector" }),
      costQuery("breakdown", { group_by: "analyzer" }),
      costQuery("breakdown", { group_by: "collection_run" }),
    ])
      .then(([summary, timeseries, account, operationCost, collectorCost, analyzerCost, collectionRun]) => {
        if (current === sequence.current && !signal.aborted) setCost({ summary, timeseries, account, operation: operationCost, collector: collectorCost, analyzer: analyzerCost, collectionRun });
      })
      .catch((error) => {
        if (!signal.aborted && current === sequence.current) setCostError(message(error, "Falha ao consultar o CloudWatch Cost Engine."));
      })
      .finally(() => {
        if (!signal.aborted && current === sequence.current) setCostLoading(false);
      });

    Promise.all([
      usageQuery("operation"),
      usageQuery("account"),
      usageQuery("collector"),
      usageQuery("analyzer"),
      usageQuery("collection_run"),
    ])
      .then(([operationUsage, account, collectorUsage, analyzerUsage, collectionRun]) => {
        if (current === sequence.current && !signal.aborted) setUsage({ operation: operationUsage, account, collector: collectorUsage, analyzer: analyzerUsage, collectionRun });
      })
      .catch((error) => {
        if (!signal.aborted && current === sequence.current) setUsageError(message(error, "Falha ao consultar a telemetria CloudWatch do DeepOps."));
      })
      .finally(() => {
        if (!signal.aborted && current === sequence.current) setUsageLoading(false);
      });

    const runParams = new URLSearchParams({
      provider: "aws",
      date_from: period.date_from,
      date_to: period.date_to,
      page: "1",
      page_size: "100",
      sort: "started_at",
      order: "desc",
    });
    if (selectedAccount) runParams.set("account_id", selectedAccount.native_account_id);
    api<CollectionPage>(`/collections?${runParams}`, { signal })
      .then((response) => {
        if (current === sequence.current && !signal.aborted) setCollections(response.items);
      })
      .catch((error) => {
        if (!signal.aborted && current === sequence.current) setRunsError(message(error, "Falha ao carregar metadados das coletas."));
      })
      .finally(() => {
        if (!signal.aborted && current === sequence.current) setRunsLoading(false);
      });

    return () => controller.abort();
  }, [canonicalFilters, period, granularity, selectedAccount, refreshToken]);

  const usageTotal = useMemo(() => summarizeUsage(usage?.operation.items ?? []), [usage]);
  const accountMap = useMemo(() => new Map(awsAccounts.map((account) => [account.native_account_id, account])), [awsAccounts]);
  const runMetadata = useMemo(() => new Map(collections.map((run) => [run.id, run])), [collections]);
  const runUsage = useMemo(() => usageByGroup(usage?.collectionRun.items ?? []), [usage]);
  const runCost = useMemo(() => {
    const grouped = new Map<string, CostItem[]>();
    for (const item of cost?.collectionRun.items ?? []) {
      if (!item.group) continue;
      const rows = grouped.get(item.group) ?? [];
      rows.push(item);
      grouped.set(item.group, rows);
    }
    return grouped;
  }, [cost]);
  const runIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of usage?.collectionRun.items ?? []) if (item.group) ids.add(item.group);
    for (const item of cost?.collectionRun.items ?? []) if (item.group) ids.add(item.group);
    return [...ids].sort((left, right) => {
      const leftTime = runMetadata.get(left)?.started_at ?? "";
      const rightTime = runMetadata.get(right)?.started_at ?? "";
      return rightTime.localeCompare(leftTime);
    }).slice(0, 20);
  }, [usage, cost, runMetadata]);
  const unassignedRunUsage = runUsage.get(null);
  const versions = pricingVersionCount(cost?.summary.items ?? []);
  const hasUsage = usageTotal.events > 0;

  return (
    <>
      <PageHeader
        eyebrow="Configurações · DeepOps"
        title="Uso e custos"
        description="Telemetria e estimativa do custo das chamadas CloudWatch geradas pelo próprio DeepOps. Não representa a fatura AWS nem o custo total de CloudWatch da conta."
        actions={<button className="button secondary" onClick={() => setRefreshToken((value) => value + 1)}><RefreshCw size={16} /> Atualizar</button>}
      />

      <section className={styles.filtersPanel} aria-label="Filtros de uso e custo">
        <div className={styles.filtersGrid}>
          <label className={styles.field}>
            <span>Período</span>
            <select value={preset} onChange={(event) => setPreset(event.target.value)}>
              {USAGE_COST_PERIOD_PRESETS.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Conta AWS</span>
            <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              <option value="">Todas as contas autorizadas</option>
              {awsAccounts.map((account) => <option value={account.id} key={account.id}>{accountLabel(account)}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Operação</span>
            <select value={operation} onChange={(event) => setOperation(event.target.value)}>
              <option value="">Todas</option>
              {options.operations.map((value) => <option value={value} key={value}>{value}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Região</span>
            <select value={region} onChange={(event) => setRegion(event.target.value)}>
              <option value="">Todas</option>
              {options.regions.map((value) => <option value={value} key={value}>{value}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Collector</span>
            <select value={collector} onChange={(event) => setCollector(event.target.value)}>
              <option value="">Todos</option>
              {options.collectors.map((value) => <option value={value} key={value}>{friendlyUsageLabel(value, "collector")}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Analyzer</span>
            <select value={analyzer} onChange={(event) => setAnalyzer(event.target.value)}>
              <option value="">Todos</option>
              {options.analyzers.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
            </select>
          </label>
        </div>
        {preset === "custom" && (
          <div className={styles.customDates}>
            <label className={styles.field}><span>De</span><input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label>
            <label className={styles.field}><span>Até</span><input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label>
          </div>
        )}
        <div className={styles.filterMeta}>
          <span>{formatUsagePeriodLabel(period)}</span>
          <span>Filtro temporal aplicado sobre <code>occurred_at</code>.</span>
        </div>
        {!period && <p className={styles.warning} role="alert">Informe um período personalizado válido.</p>}
        {optionsError && <p className={styles.warning} role="alert">{optionsError}</p>}
      </section>

      {cost?.summary && !cost.summary.is_complete && (
        <div className={styles.warningBanner} role="alert">
          <strong>Estimativa incompleta.</strong> Parte do uso ainda não possui regra de pricing válida; o valor monetário exibido é parcial.
        </div>
      )}

      <div className={styles.kpiGrid}>
        <article className={styles.kpiCard}>
          <span>Custo estimado do DeepOps</span>
          {costLoading ? <strong>Carregando…</strong> : costError ? <strong>Indisponível</strong> : <CostTotals totals={cost?.summary.totals ?? []} />}
          <small>Estimativa bruta retornada pelo CloudWatch Cost Engine.</small>
        </article>
        <article className={styles.kpiCard}>
          <span>Requests CloudWatch</span>
          <strong>{usageLoading ? "Carregando…" : formatUsageNumber(usageTotal.requests)}</strong>
          <small>Requests observados pela telemetria no período.</small>
        </article>
        <article className={styles.kpiCard}>
          <span>Metric queries</span>
          <strong>{usageLoading ? "Carregando…" : formatUsageNumber(usageTotal.metric_queries)}</strong>
          <small>Exibidas separadamente; não são somadas a requests.</small>
        </article>
        <article className={styles.kpiCard}>
          <span>Falhas</span>
          <strong>{usageLoading ? "Carregando…" : formatUsageNumber(usageTotal.failed_events)}</strong>
          <small>Uma execução com falha pode ter requests e custo estimado.</small>
        </article>
      </div>

      {usageError && <div className={styles.errorBanner} role="alert"><strong>Erro de telemetria.</strong> {usageError}</div>}
      {costError && <div className={styles.errorBanner} role="alert"><strong>Erro de pricing/custo.</strong> {costError} A telemetria continua sendo apresentada quando disponível.</div>}

      {!usageLoading && !usageError && !hasUsage && (
        <section className={styles.emptyState}>
          <h2>Nenhum uso CloudWatch do DeepOps foi registrado neste período.</h2>
          <p>A telemetria começa a aparecer após novas coletas AWS instrumentadas; nenhum histórico anterior à instrumentação é estimado artificialmente.</p>
        </section>
      )}

      {hasUsage && cost?.summary && cost.summary.totals.length === 0 && cost.summary.unpriced_events > 0 && (
        <div className={styles.warningBanner} role="alert">Uso coletado, mas o custo não pôde ser estimado para o recorte porque não há regra de pricing aplicável.</div>
      )}

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div><h2>Custo estimado ao longo do tempo</h2><p>Valores calculados pelo backend com a regra vigente no timestamp factual de cada usage event.</p></div>
          {cost?.summary && !cost.summary.is_complete && <span className={styles.warningBadge}>Série monetária parcial</span>}
        </div>
        <div className={styles.panelBody}>
          {costLoading ? <div className={styles.sectionState}>Carregando evolução de custo…</div> : costError ? <div className={styles.sectionError}>Não foi possível carregar a série de custo.</div> : cost ? <CostChart response={cost.timeseries} /> : null}
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>Uso técnico</h2><p>Dimensões técnicas permanecem separadas para evitar somar unidades incompatíveis.</p></div></div>
        <div className={styles.panelBody}>
          {usageLoading ? <div className={styles.sectionState}>Carregando uso técnico…</div> : usageError ? <div className={styles.sectionError}>Não foi possível carregar a telemetria.</div> : (
            <div className={styles.usageGrid}>
              <div><span>Eventos</span><strong>{formatUsageNumber(usageTotal.events)}</strong></div>
              <div><span>Requests</span><strong>{formatUsageNumber(usageTotal.requests)}</strong></div>
              <div><span>Metric queries</span><strong>{formatUsageNumber(usageTotal.metric_queries)}</strong></div>
              <div><span>Métricas solicitadas</span><strong>{formatUsageNumber(usageTotal.metrics_requested)}</strong></div>
            </div>
          )}
        </div>
      </section>

      {cost && usage && (
        <div className={styles.breakdownGrid}>
          <BreakdownSection title="Custo por conta" subtitle="Conta amigável e AWS Account ID, com custo separado por currency." kind="account" cost={cost.account} usage={usage.account} accounts={awsAccounts} />
          <BreakdownSection title="Custo por operação" subtitle="Driver técnico de custo com provenance da regra aplicada." kind="operation" cost={cost.operation} usage={usage.operation} accounts={awsAccounts} showProvenance />
          <BreakdownSection title="Custo por collector" subtitle="Quanto cada coleta instrumentada representa no custo estimado." kind="collector" cost={cost.collector} usage={usage.collector} accounts={awsAccounts} />
          <BreakdownSection title="Custo por analyzer" subtitle="Somente attribution factual; uso compartilhado não é redistribuído." kind="analyzer" cost={cost.analyzer} usage={usage.analyzer} accounts={awsAccounts} />
        </div>
      )}

      {cost?.summary.unpriced_usage && cost.summary.unpriced_usage.length > 0 && (
        <section className={styles.panel}>
          <div className={styles.panelHeader}><div><h2>Uso sem precificação</h2><p>Usage factual preservado que ainda não encontrou regra de pricing válida.</p></div><span className={styles.warningBadge}>{formatUsageNumber(cost.summary.unpriced_events)} eventos</span></div>
          <div className={styles.panelBody}>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th>Operação</th><th>Região</th><th>Eventos</th><th>Requests</th><th>Motivo</th></tr></thead>
                <tbody>{cost.summary.unpriced_usage.map((item) => <tr key={`${item.operation}-${item.region}`}><td>{item.operation}</td><td>{item.region}</td><td>{formatUsageNumber(item.events)}</td><td>{formatUsageNumber(item.requests)}</td><td>{item.reason}</td></tr>)}</tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>Execuções recentes</h2><p>CollectionRuns que produziram usage no recorte atual. FAILED não implica custo zero.</p></div></div>
        <div className={styles.panelBody}>
          {runsLoading || usageLoading || costLoading ? <div className={styles.sectionState}>Carregando execuções…</div> : runsError ? <div className={styles.sectionError}>{runsError}</div> : runIds.length === 0 ? <div className={styles.sectionState}>Nenhuma CollectionRun com usage no recorte.</div> : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th>CollectionRun</th><th>Início</th><th>Conta</th><th>Status</th><th>Requests</th><th>Metric queries</th><th>Custo estimado</th></tr></thead>
                <tbody>
                  {runIds.map((runId) => {
                    const run = runMetadata.get(runId);
                    const technical = runUsage.get(runId);
                    const costs = runCost.get(runId) ?? [];
                    const account = run ? accountMap.get(run.account_id) : undefined;
                    return (
                      <tr key={runId}>
                        <td><Link href={`/collections/${runId}`}>{runId.slice(0, 8)}…</Link></td>
                        <td>{formatUsageCostDate(run?.started_at)}</td>
                        <td>{run ? (account ? accountLabel(account) : run.account_name || run.account_id) : "—"}</td>
                        <td><span className={run?.status === "FAILED" ? styles.failedStatus : styles.status}>{run?.status ?? "—"}</span></td>
                        <td>{formatUsageNumber(technical?.requests ?? 0)}</td>
                        <td>{formatUsageNumber(technical?.metric_queries ?? 0)}</td>
                        <td>{costs.length ? costs.map((item) => <div key={item.currency}>{formatUsageCostMoney(item.gross_estimated_cost, item.currency)}</div>) : "Sem custo precificado"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {unassignedRunUsage && <p className={styles.note}>{formatUsageNumber(unassignedRunUsage.requests)} requests do recorte não estão atribuídos a uma CollectionRun específica.</p>}
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>Sobre esta estimativa</h2><p>Premissas e provenance do CloudWatch Cost Engine.</p></div></div>
        <div className={styles.assumptions}>
          <div><span>Definição</span><strong>Estimativa do custo das chamadas CloudWatch geradas pelo próprio DeepOps</strong><p>Não é o custo total de CloudWatch da conta e não é a fatura final da AWS.</p></div>
          <div><span>Fonte de pricing</span><strong>{cost?.summary.pricing_sources.length ? cost.summary.pricing_sources.map(sourceLabel).join(", ") : "Sem regra aplicada no recorte"}</strong><p>Verificado em {formatUsageCostDate(cost?.summary.pricing_verified_at)}.</p></div>
          <div><span>Free tier</span><strong>{cost?.summary.free_tier_applied ? "Aplicado pelo Cost Engine" : "Não aplicado"}</strong><p>Por padrão, a estimativa é bruta: o DeepOps não conhece necessariamente o consumo compartilhado do free tier por outras workloads da conta.</p></div>
          <div><span>Completude</span><strong>{cost?.summary.is_complete ? "Completa para as regras disponíveis" : "Incompleta"}</strong><p>{cost?.summary.unpriced_events ?? 0} eventos sem pricing; {cost?.summary.inexact_request_events ?? 0} eventos com request count inexato.</p></div>
          <div><span>Vigências</span><strong>{versions > 1 ? `${versions} versões de pricing aplicadas` : versions === 1 ? "1 versão de pricing aplicada" : "Nenhuma versão aplicada"}</strong><p>O frontend não usa o preço atual para recalcular histórico.</p></div>
          <div><span>Moeda</span><strong>Sem conversão cambial</strong><p>Moedas são exibidas separadamente e nunca somadas entre si.</p></div>
        </div>
        {cost?.summary.estimation_basis && <p className={styles.estimationBasis}>{cost.summary.estimation_basis}</p>}
      </section>
    </>
  );
}
