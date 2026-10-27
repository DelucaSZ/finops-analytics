"use client";

import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { CurrencyDisplay, PercentageDisplay, StatusIndicator, type ProductStatus } from "@/components/aven";
import type { BillingGranularity, BillingGroupBy } from "@/lib/billing";
import {
  aggregateBillingStatuses,
  billingStatusHasForecast,
  billingStatusIsEstimated,
  billingStatusLabel,
  formatBillingAxisDate,
  formatBillingAxisMoney,
  formatBillingDate,
  formatBillingRange,
} from "@/lib/billing-dashboard.mjs";
import type {
  BillingChartDataset,
  BillingChartPeriod,
  BillingDataStatus,
} from "@/lib/billing-dashboard.mjs";
import styles from "./billing.module.css";

const GRANULARITY_LABELS: Record<BillingGranularity, string> = {
  DAILY: "Diária",
  MONTHLY: "Mensal",
};

const GROUP_BY_LABELS: Record<BillingGroupBy, string> = {
  NONE: "Sem agrupamento",
  SERVICE: "Serviço",
  ACCOUNT: "Conta",
};

const SERIES_COLORS = [
  "var(--chart-series-1)",
  "var(--chart-series-2)",
  "var(--chart-series-3)",
  "var(--chart-series-4)",
  "var(--chart-series-5)",
  "var(--chart-series-6)",
] as const;

const MAX_SERVICE_SERIES = SERIES_COLORS.length;
const OTHER_SERIES_KEY = "__billing_other__";
const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 360;
const MARGIN = { top: 28, right: 24, bottom: 58, left: 88 };

type HoveredBucket = {
  periodIndex: number;
  seriesKey: string | null;
};

function stackBounds(period: BillingChartPeriod) {
  let positive = 0;
  let negative = 0;
  for (const item of period.series) {
    if (item.amount >= 0) positive += item.amount;
    else negative += item.amount;
  }
  return { positive, negative };
}

function formatShare(amount: number, total: number) {
  if (!Number.isFinite(amount) || !Number.isFinite(total) || Math.abs(total) < Number.EPSILON) return null;
  return Math.abs(amount) / Math.abs(total);
}

function statusOpacity(status: BillingDataStatus) {
  switch (status) {
    case "FORECAST":
      return 0.48;
    case "INCLUDES_FORECAST":
      return 0.6;
    case "ESTIMATED":
      return 0.78;
    case "PARTIALLY_ESTIMATED":
      return 0.7;
    case "ACTUAL":
    default:
      return 1;
  }
}

function statusMarker(status: BillingDataStatus) {
  switch (status) {
    case "FORECAST":
    case "INCLUDES_FORECAST":
      return "F";
    case "ESTIMATED":
      return "*";
    case "PARTIALLY_ESTIMATED":
      return "≈";
    case "ACTUAL":
    default:
      return null;
  }
}

function statusSemantic(status: BillingDataStatus): ProductStatus {
  switch (status) {
    case "ACTUAL":
      return "success";
    case "FORECAST":
    case "INCLUDES_FORECAST":
      return "info";
    case "ESTIMATED":
    case "PARTIALLY_ESTIMATED":
    default:
      return "warning";
  }
}

function compactServiceDataset(dataset: BillingChartDataset, groupBy: BillingGroupBy) {
  if (groupBy !== "SERVICE" || dataset.series.length <= MAX_SERVICE_SERIES) return dataset;

  const visibleSeries = dataset.series.slice(0, MAX_SERVICE_SERIES - 1);
  const visibleKeys = new Set(visibleSeries.map((item) => item.key));
  const hiddenSeries = dataset.series.slice(MAX_SERVICE_SERIES - 1);
  const otherTotal = hiddenSeries.reduce((sum, item) => sum + item.total, 0);
  const series = [
    ...visibleSeries,
    { key: OTHER_SERIES_KEY, label: "Outros", total: otherTotal },
  ];

  const periods = dataset.periods.map((period) => {
    const visibleItems = period.series.filter((item) => visibleKeys.has(item.key));
    const hiddenItems = period.series.filter((item) => !visibleKeys.has(item.key));
    const otherAmount = hiddenItems.reduce((sum, item) => sum + item.amount, 0);
    const otherStatus = aggregateBillingStatuses(hiddenItems.map((item) => item.status));

    return {
      ...period,
      series: otherAmount === 0 && hiddenItems.length === 0
        ? visibleItems
        : [
            ...visibleItems,
            {
              key: OTHER_SERIES_KEY,
              label: "Outros",
              amount: otherAmount,
              status: otherStatus,
              estimated: billingStatusIsEstimated(otherStatus),
            },
          ],
    };
  });

  return { ...dataset, series, periods };
}

function colorIndexForKey(key: string) {
  if (key === OTHER_SERIES_KEY) return SERIES_COLORS.length - 1;
  let hash = 0;
  for (let index = 0; index < key.length; index += 1) {
    hash = ((hash << 5) - hash + key.charCodeAt(index)) | 0;
  }
  return Math.abs(hash) % SERIES_COLORS.length;
}

function seriesColor(key: string) {
  return SERIES_COLORS[colorIndexForKey(key)];
}

function tooltipAlignment(periodIndex: number, totalPeriods: number) {
  if (periodIndex <= 1) return "start";
  if (periodIndex >= totalPeriods - 2) return "end";
  return "center";
}

export function BillingCostChart({
  dataset,
  granularity,
  groupBy,
}: {
  dataset: BillingChartDataset;
  granularity: BillingGranularity;
  groupBy: BillingGroupBy;
}) {
  const [hovered, setHovered] = useState<HoveredBucket | null>(null);
  const chartDataset = useMemo(
    () => compactServiceDataset(dataset, groupBy),
    [dataset, groupBy],
  );
  const { currency, periods, series } = chartDataset;

  if (!periods.length) return null;

  const innerWidth = VIEWBOX_WIDTH - MARGIN.left - MARGIN.right;
  const innerHeight = VIEWBOX_HEIGHT - MARGIN.top - MARGIN.bottom;
  const slotWidth = innerWidth / Math.max(periods.length, 1);
  const barWidth = Math.max(4, Math.min(groupBy === "NONE" ? 34 : 42, slotWidth * 0.7));
  const bounds = periods.map(stackBounds);
  let minimum = Math.min(0, ...bounds.map((item) => item.negative));
  let maximum = Math.max(0, ...bounds.map((item) => item.positive));
  if (minimum === maximum) maximum = minimum === 0 ? 1 : minimum + Math.abs(minimum) * 0.1;
  const rawSpan = maximum - minimum || 1;
  const padding = rawSpan * 0.06;
  if (minimum < 0) minimum -= padding;
  if (maximum > 0) maximum += padding;
  const span = maximum - minimum || 1;
  const y = (value: number) => MARGIN.top + ((maximum - value) / span) * innerHeight;
  const zeroY = y(0);
  const tickCount = 5;
  const yTicks = Array.from(
    { length: tickCount },
    (_, index) => minimum + (span * index) / (tickCount - 1),
  );
  const xTickStride = Math.max(1, Math.ceil(periods.length / 9));
  const rotateLabels = periods.length > 12;
  const hoveredPeriod = hovered ? periods[hovered.periodIndex] : null;
  const hoveredXPercent = hovered
    ? ((MARGIN.left + slotWidth * hovered.periodIndex + slotWidth / 2) / VIEWBOX_WIDTH) * 100
    : 0;
  const periodRange = {
    start_date: periods[0].start_date,
    end_date: periods[periods.length - 1].end_date,
  };
  const hoveredSeries = hoveredPeriod
    ? [...hoveredPeriod.series].sort((left, right) => Math.abs(right.amount) - Math.abs(left.amount))
    : [];

  return (
    <section className={styles.chartGroup} aria-label={`Análise de custos em ${currency}`}>
      <div className={styles.chartContextGrid}>
        <div>
          <span>Custo total</span>
          <strong>
            <CurrencyDisplay
              value={chartDataset.total}
              currency={currency}
              locale="pt-BR"
              currencyDisplay="code"
              minimumFractionDigits={2}
              maximumFractionDigits={2}
            />
          </strong>
        </div>
        <div>
          <span>Período</span>
          <strong>{formatBillingRange(periodRange)}</strong>
        </div>
        <div>
          <span>Granularidade</span>
          <strong>{GRANULARITY_LABELS[granularity]}</strong>
        </div>
        <div>
          <span>Agrupamento</span>
          <strong>{GROUP_BY_LABELS[groupBy]}</strong>
        </div>
        {chartDataset.status !== "ACTUAL" && (
          <StatusIndicator
            status={statusSemantic(chartDataset.status)}
            label={billingStatusLabel(chartDataset.status)}
          />
        )}
      </div>

      {groupBy !== "NONE" && series.length > 0 && (
        <div className={styles.chartLegend} aria-label="Legenda de séries">
          {series.map((item) => (
            <span key={item.key} title={item.label}>
              <i style={{ background: seriesColor(item.key) }} aria-hidden="true" />
              <b>{item.label}</b>
            </span>
          ))}
        </div>
      )}

      <div
        className={styles.chartViewport}
        onMouseLeave={() => setHovered(null)}
      >
        <svg
          className={styles.chart}
          viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
          role="img"
          aria-label={`Custos em ${currency}, ${GRANULARITY_LABELS[granularity].toLowerCase()}, agrupamento ${GROUP_BY_LABELS[groupBy].toLowerCase()}. Use Tab para percorrer os períodos e consultar valores detalhados.`}
          preserveAspectRatio="xMidYMid meet"
        >
          <text
            x={18}
            y={VIEWBOX_HEIGHT / 2}
            textAnchor="middle"
            className={styles.axisTitle}
            transform={`rotate(-90 18 ${VIEWBOX_HEIGHT / 2})`}
          >
            Custo ({currency})
          </text>

          {yTicks.map((tick) => {
            const tickY = y(tick);
            return (
              <g key={tick}>
                <line
                  x1={MARGIN.left}
                  x2={VIEWBOX_WIDTH - MARGIN.right}
                  y1={tickY}
                  y2={tickY}
                  className={styles.gridLine}
                />
                <text
                  x={MARGIN.left - 12}
                  y={tickY + 4}
                  textAnchor="end"
                  className={styles.axisLabel}
                >
                  {formatBillingAxisMoney(tick, currency)}
                </text>
              </g>
            );
          })}

          <line
            x1={MARGIN.left}
            x2={VIEWBOX_WIDTH - MARGIN.right}
            y1={zeroY}
            y2={zeroY}
            className={styles.zeroLine}
          />

          {periods.map((period, periodIndex) => {
            const centerX = MARGIN.left + slotWidth * periodIndex + slotWidth / 2;
            const marker = statusMarker(period.status);
            let positiveBase = 0;
            let negativeBase = 0;
            const periodLabel = `${formatBillingDate(period.start_date)} · ${billingStatusLabel(period.status)}`;
            return (
              <g key={`${period.start_date}-${period.end_date}`}>
                <rect
                  x={MARGIN.left + slotWidth * periodIndex}
                  y={MARGIN.top}
                  width={slotWidth}
                  height={innerHeight}
                  className={styles.hoverBand}
                  tabIndex={0}
                  role="button"
                  aria-label={`${periodLabel}. Total ${currency} ${period.total}.`}
                  onFocus={() => setHovered({ periodIndex, seriesKey: null })}
                  onBlur={() => setHovered(null)}
                  onMouseEnter={() => setHovered({ periodIndex, seriesKey: null })}
                />
                {period.series.map((item) => {
                  if (item.amount === 0) return null;
                  const startValue = item.amount >= 0 ? positiveBase : negativeBase;
                  const endValue = startValue + item.amount;
                  if (item.amount >= 0) positiveBase = endValue;
                  else negativeBase = endValue;
                  const rectY = Math.min(y(startValue), y(endValue));
                  const rectHeight = Math.max(1, Math.abs(y(startValue) - y(endValue)));
                  const hasForecast = billingStatusHasForecast(item.status);
                  return (
                    <rect
                      key={item.key}
                      x={centerX - barWidth / 2}
                      y={rectY}
                      width={barWidth}
                      height={rectHeight}
                      fill={seriesColor(item.key)}
                      fillOpacity={statusOpacity(item.status)}
                      stroke={hasForecast ? "var(--chart-forecast)" : undefined}
                      strokeDasharray={hasForecast ? "4 3" : undefined}
                      strokeWidth={hasForecast ? 1.25 : undefined}
                      className={styles.chartBar}
                      onMouseEnter={() => setHovered({ periodIndex, seriesKey: item.key })}
                    >
                      <title>{`${periodLabel} · ${item.label} · ${currency} ${item.amount}`}</title>
                    </rect>
                  );
                })}
                {(periodIndex % xTickStride === 0 || periodIndex === periods.length - 1) && (
                  <text
                    x={centerX}
                    y={VIEWBOX_HEIGHT - 24}
                    textAnchor={rotateLabels ? "end" : "middle"}
                    className={styles.axisLabel}
                    transform={rotateLabels ? `rotate(-28 ${centerX} ${VIEWBOX_HEIGHT - 24})` : undefined}
                  >
                    {formatBillingAxisDate(period.start_date, granularity)}
                  </text>
                )}
                {marker && (
                  <text
                    x={centerX}
                    y={MARGIN.top + 12}
                    textAnchor="middle"
                    className={styles.estimatedMark}
                  >
                    <title>{billingStatusLabel(period.status)}</title>
                    {marker}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {hoveredPeriod && hovered && (
          <div
            className={styles.chartTooltip}
            role="tooltip"
            data-alignment={tooltipAlignment(hovered.periodIndex, periods.length)}
            style={{ "--billing-tooltip-left": `${hoveredXPercent}%` } as CSSProperties}
          >
            <div className={styles.tooltipHeading}>
              <strong>{formatBillingDate(hoveredPeriod.start_date)}</strong>
              <StatusIndicator
                status={statusSemantic(hoveredPeriod.status)}
                label={billingStatusLabel(hoveredPeriod.status)}
              />
            </div>
            {hoveredSeries.length > 0 && (
              <div className={styles.tooltipSeries}>
                {hoveredSeries.map((item) => {
                  const share = formatShare(item.amount, hoveredPeriod.total);
                  return (
                    <div
                      key={item.key}
                      className={hovered.seriesKey === item.key ? styles.tooltipSeriesActive : undefined}
                      onMouseEnter={() => setHovered((current) => current ? { ...current, seriesKey: item.key } : current)}
                    >
                      <i style={{ background: seriesColor(item.key) }} aria-hidden="true" />
                      <span title={item.label}>{item.label}</span>
                      <strong>
                        <CurrencyDisplay
                          value={item.amount}
                          currency={currency}
                          locale="pt-BR"
                          currencyDisplay="code"
                          minimumFractionDigits={2}
                          maximumFractionDigits={2}
                        />
                        {share !== null && (
                          <>
                            {" · "}
                            <PercentageDisplay
                              value={share}
                              valueMode="fraction"
                              locale="pt-BR"
                              maximumFractionDigits={1}
                            />
                          </>
                        )}
                      </strong>
                    </div>
                  );
                })}
              </div>
            )}
            <div className={styles.tooltipTotal}>
              <span>Total do período</span>
              <strong>
                <CurrencyDisplay
                  value={hoveredPeriod.total}
                  currency={currency}
                  locale="pt-BR"
                  currencyDisplay="code"
                  minimumFractionDigits={2}
                  maximumFractionDigits={2}
                />
              </strong>
            </div>
          </div>
        )}
      </div>

      <div className={styles.chartNotes}>
        {dataset.series.length > series.length && groupBy === "SERVICE" && (
          <p>Serviços de menor custo foram consolidados em “Outros” para manter a leitura do gráfico.</p>
        )}
        {chartDataset.estimated && (
          <p>* / ≈ identificam somente buckets estimados ou parcialmente estimados informados pelo Cost Explorer.</p>
        )}
        {billingStatusHasForecast(chartDataset.status) && (
          <p>F identifica forecast; os buckets previstos mantêm a cor da série e usam contorno tracejado.</p>
        )}
      </div>
    </section>
  );
}
