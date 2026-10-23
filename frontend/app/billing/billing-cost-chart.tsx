"use client";

import { useMemo, useState } from "react";
import type { BillingGranularity, BillingGroupBy } from "@/lib/billing";
import {
  aggregateBillingStatuses,
  billingStatusHasForecast,
  billingStatusIsEstimated,
  billingStatusLabel,
  formatBillingAxisDate,
  formatBillingAxisMoney,
  formatBillingDate,
  formatBillingMoney,
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
  "var(--accent)",
  "var(--blue)",
  "var(--violet)",
  "var(--warning)",
  "var(--danger)",
  "var(--accent-2)",
  "var(--muted-2)",
  "var(--border-strong)",
];

const MAX_SERVICE_SERIES = SERIES_COLORS.length;
const OTHER_SERIES_KEY = "__billing_other__";
const TOOLTIP_EDGE_SPACE = 190;

type TooltipAlignment = "start" | "center" | "end";

type HoveredBucket = {
  periodIndex: number;
  seriesKey: string | null;
  tooltipAlignment: TooltipAlignment;
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

function tooltipTransform(alignment: TooltipAlignment) {
  if (alignment === "start") return "translateX(0)";
  if (alignment === "end") return "translateX(-100%)";
  return "translateX(-50%)";
}

function tooltipAlignmentForPointer(clientX: number): TooltipAlignment {
  if (typeof window === "undefined") return "center";
  if (clientX < TOOLTIP_EDGE_SPACE) return "start";
  if (clientX > window.innerWidth - TOOLTIP_EDGE_SPACE) return "end";
  return "center";
}

function hoveredBucket(periodIndex: number, seriesKey: string | null, clientX: number): HoveredBucket {
  return {
    periodIndex,
    seriesKey,
    tooltipAlignment: tooltipAlignmentForPointer(clientX),
  };
}

function formatShare(amount: number, total: number) {
  if (!Number.isFinite(amount) || !Number.isFinite(total) || Math.abs(total) < 1e-9) return "0%";
  return new Intl.NumberFormat("pt-BR", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Math.abs(amount) / Math.abs(total));
}

function statusOpacity(status: BillingDataStatus) {
  switch (status) {
    case "FORECAST":
      return 0.46;
    case "INCLUDES_FORECAST":
      return 0.58;
    case "ESTIMATED":
      return 0.76;
    case "PARTIALLY_ESTIMATED":
      return 0.68;
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
  const colorBySeries = useMemo(
    () => new Map(series.map((item, index) => [item.key, SERIES_COLORS[index % SERIES_COLORS.length]])),
    [series],
  );

  if (!periods.length) return null;

  const margin = { top: 24, right: 26, bottom: 62, left: 92 };
  const preferredSlot = granularity === "DAILY" ? 28 : 52;
  const width = Math.max(960, Math.min(3200, margin.left + margin.right + periods.length * preferredSlot));
  const height = 390;
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const slotWidth = innerWidth / Math.max(periods.length, 1);
  const barWidth = Math.max(3, Math.min(groupBy === "NONE" ? 34 : 42, slotWidth * 0.68));
  const bounds = periods.map(stackBounds);
  let minimum = Math.min(0, ...bounds.map((item) => item.negative));
  let maximum = Math.max(0, ...bounds.map((item) => item.positive));
  if (minimum === maximum) maximum = minimum === 0 ? 1 : minimum + Math.abs(minimum) * 0.1;
  const rawSpan = maximum - minimum || 1;
  const padding = rawSpan * 0.06;
  if (minimum < 0) minimum -= padding;
  if (maximum > 0) maximum += padding;
  const span = maximum - minimum || 1;
  const y = (value: number) => margin.top + ((maximum - value) / span) * innerHeight;
  const zeroY = y(0);
  const tickCount = 5;
  const yTicks = Array.from(
    { length: tickCount },
    (_, index) => minimum + (span * index) / (tickCount - 1),
  );
  const xTickStride = Math.max(1, Math.ceil(periods.length / 9));
  const rotateLabels = periods.length > 12;
  const hoveredPeriod = hovered ? periods[hovered.periodIndex] : null;
  const hoveredX = hovered
    ? margin.left + slotWidth * hovered.periodIndex + slotWidth / 2
    : 0;
  const periodRange = {
    start_date: periods[0].start_date,
    end_date: periods[periods.length - 1].end_date,
  };

  return (
    <div className={styles.chartGroup}>
      <div className={styles.chartContextGrid}>
        <div>
          <span>Custo total · {currency}</span>
          <strong>{formatBillingMoney(chartDataset.total, currency)}</strong>
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
          <span className={styles.estimatedBadge}>{billingStatusLabel(chartDataset.status)}</span>
        )}
      </div>

      {groupBy !== "NONE" && series.length > 0 && (
        <div className={styles.chartLegend} aria-label="Legenda do gráfico">
          {series.map((item) => (
            <span key={item.key} title={item.label}>
              <i style={{ background: colorBySeries.get(item.key) }} />
              <b>{item.label}</b>
            </span>
          ))}
        </div>
      )}

      <div className={styles.chartScroll}>
        <div
          className={styles.chartCanvas}
          style={{ minWidth: `${width}px` }}
          onMouseLeave={() => setHovered(null)}
        >
          <svg
            className={styles.chart}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Custos em ${currency}, ${GRANULARITY_LABELS[granularity].toLowerCase()}, agrupamento ${GROUP_BY_LABELS[groupBy].toLowerCase()}.`}
          >
            <text
              x={18}
              y={height / 2}
              textAnchor="middle"
              className={styles.axisTitle}
              transform={`rotate(-90 18 ${height / 2})`}
            >
              Custo ({currency})
            </text>

            {yTicks.map((tick) => {
              const tickY = y(tick);
              return (
                <g key={tick}>
                  <line
                    x1={margin.left}
                    x2={width - margin.right}
                    y1={tickY}
                    y2={tickY}
                    className={styles.gridLine}
                  />
                  <text
                    x={margin.left - 12}
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
              x1={margin.left}
              x2={width - margin.right}
              y1={zeroY}
              y2={zeroY}
              className={styles.zeroLine}
            />

            {periods.map((period, periodIndex) => {
              const centerX = margin.left + slotWidth * periodIndex + slotWidth / 2;
              const marker = statusMarker(period.status);
              let positiveBase = 0;
              let negativeBase = 0;
              return (
                <g key={`${period.start_date}-${period.end_date}`}>
                  <rect
                    x={margin.left + slotWidth * periodIndex}
                    y={margin.top}
                    width={slotWidth}
                    height={innerHeight}
                    className={styles.hoverBand}
                    onMouseEnter={(event) => setHovered(hoveredBucket(periodIndex, null, event.clientX))}
                  />
                  {period.series.map((item) => {
                    if (item.amount === 0) return null;
                    const startValue = item.amount >= 0 ? positiveBase : negativeBase;
                    const endValue = startValue + item.amount;
                    if (item.amount >= 0) positiveBase = endValue;
                    else negativeBase = endValue;
                    const rectY = Math.min(y(startValue), y(endValue));
                    const rectHeight = Math.max(1, Math.abs(y(startValue) - y(endValue)));
                    const fill = colorBySeries.get(item.key) || SERIES_COLORS[0];
                    const hasForecast = billingStatusHasForecast(item.status);
                    return (
                      <rect
                        key={item.key}
                        x={centerX - barWidth / 2}
                        y={rectY}
                        width={barWidth}
                        height={rectHeight}
                        rx={groupBy === "NONE" ? 2 : 1}
                        fill={fill}
                        fillOpacity={statusOpacity(item.status)}
                        stroke={hasForecast ? "var(--text)" : undefined}
                        strokeDasharray={hasForecast ? "4 3" : undefined}
                        strokeWidth={hasForecast ? 1.25 : undefined}
                        className={styles.chartBar}
                        onMouseEnter={(event) => setHovered(hoveredBucket(periodIndex, item.key, event.clientX))}
                      >
                        <title>{`${formatBillingDate(period.start_date)} · ${billingStatusLabel(period.status)} · ${item.label} · ${formatBillingMoney(item.amount, currency)} · ${formatShare(item.amount, period.total)}`}</title>
                      </rect>
                    );
                  })}
                  {(periodIndex % xTickStride === 0 || periodIndex === periods.length - 1) && (
                    <text
                      x={centerX}
                      y={height - 25}
                      textAnchor={rotateLabels ? "end" : "middle"}
                      className={styles.axisLabel}
                      transform={rotateLabels ? `rotate(-28 ${centerX} ${height - 25})` : undefined}
                    >
                      {formatBillingAxisDate(period.start_date, granularity)}
                    </text>
                  )}
                  {marker && (
                    <text
                      x={centerX}
                      y={margin.top + 12}
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
              style={{
                left: `${(hoveredX / width) * 100}%`,
                transform: tooltipTransform(hovered.tooltipAlignment),
              }}
            >
              <div className={styles.tooltipHeading}>
                <strong>{formatBillingDate(hoveredPeriod.start_date)}</strong>
                <span>{billingStatusLabel(hoveredPeriod.status)}</span>
              </div>
              {hoveredPeriod.series.length > 0 && (
                <div className={styles.tooltipSeries}>
                  {hoveredPeriod.series.map((item) => (
                    <div
                      key={item.key}
                      className={hovered.seriesKey === item.key ? styles.tooltipSeriesActive : undefined}
                      onMouseEnter={() => setHovered((current) => current ? { ...current, seriesKey: item.key } : current)}
                    >
                      <i style={{ background: colorBySeries.get(item.key) || SERIES_COLORS[0] }} />
                      <span title={item.label}>{item.label}</span>
                      <strong>{formatBillingMoney(item.amount, currency)} · {formatShare(item.amount, hoveredPeriod.total)}</strong>
                    </div>
                  ))}
                </div>
              )}
              <div className={styles.tooltipTotal}>
                <span>Total do período</span>
                <strong>{formatBillingMoney(hoveredPeriod.total, currency)}</strong>
              </div>
            </div>
          )}
        </div>
      </div>

      {dataset.series.length > series.length && groupBy === "SERVICE" && (
        <p className={styles.chartNote}>Serviços de menor custo foram consolidados em “Outros” para manter a leitura do gráfico.</p>
      )}
      {chartDataset.estimated && (
        <p className={styles.chartNote}>* / ≈ indicam buckets provisórios conforme o AWS Cost Explorer.</p>
      )}
      {billingStatusHasForecast(chartDataset.status) && (
        <p className={styles.chartNote}>F indica forecast; barras previstas mantêm a cor do serviço e usam contorno tracejado.</p>
      )}
    </div>
  );
}
