"use client";

import { useMemo, useState } from "react";
import type { BillingGranularity, BillingGroupBy } from "@/lib/billing";
import {
  formatBillingAxisDate,
  formatBillingAxisMoney,
  formatBillingDate,
  formatBillingMoney,
  formatBillingRange,
} from "@/lib/billing-dashboard.mjs";
import type {
  BillingChartDataset,
  BillingChartPeriod,
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

function tooltipTransform(x: number, width: number) {
  if (x < width * 0.25) return "translateX(0)";
  if (x > width * 0.75) return "translateX(-100%)";
  return "translateX(-50%)";
}

function formatShare(amount: number, total: number) {
  if (!Number.isFinite(amount) || !Number.isFinite(total) || Math.abs(total) < 1e-9) return "0%";
  return new Intl.NumberFormat("pt-BR", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Math.abs(amount) / Math.abs(total));
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
    const otherEstimated = hiddenItems.some((item) => item.estimated);

    return {
      ...period,
      series: otherAmount === 0 && !otherEstimated
        ? visibleItems
        : [
            ...visibleItems,
            {
              key: OTHER_SERIES_KEY,
              label: "Outros",
              amount: otherAmount,
              estimated: otherEstimated,
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
        {chartDataset.estimated && <span className={styles.estimatedBadge}>Inclui dados estimados</span>}
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
        <div className={styles.chartCanvas} style={{ minWidth: `${width}px` }}>
          <svg
            className={styles.chart}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Custos em ${currency}, ${GRANULARITY_LABELS[granularity].toLowerCase()}, agrupamento ${GROUP_BY_LABELS[groupBy].toLowerCase()}.`}
            onMouseLeave={() => setHovered(null)}
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
                    const fill = colorBySeries.get(item.key) || SERIES_COLORS[0];
                    return (
                      <rect
                        key={item.key}
                        x={centerX - barWidth / 2}
                        y={rectY}
                        width={barWidth}
                        height={rectHeight}
                        rx={groupBy === "NONE" ? 2 : 1}
                        fill={fill}
                        className={styles.chartBar}
                        onMouseEnter={() => setHovered({ periodIndex, seriesKey: item.key })}
                      >
                        <title>{`${formatBillingDate(period.start_date)} · ${item.label} · ${formatBillingMoney(item.amount, currency)} · ${formatShare(item.amount, period.total)}`}</title>
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
                  {period.estimated && (
                    <text x={centerX} y={margin.top + 12} textAnchor="middle" className={styles.estimatedMark}>*</text>
                  )}
                </g>
              );
            })}
          </svg>

          {hoveredPeriod && (
            <div
              className={styles.chartTooltip}
              style={{
                left: `${(hoveredX / width) * 100}%`,
                transform: tooltipTransform(hoveredX, width),
              }}
            >
              <div className={styles.tooltipHeading}>
                <strong>{formatBillingDate(hoveredPeriod.start_date)}</strong>
                {hoveredPeriod.estimated && <span>Estimado</span>}
              </div>
              {hoveredPeriod.series.length > 0 && (
                <div className={styles.tooltipSeries}>
                  {hoveredPeriod.series.map((item) => (
                    <div
                      key={item.key}
                      className={hovered?.seriesKey === item.key ? styles.tooltipSeriesActive : undefined}
                    >
                      <i style={{ background: colorBySeries.get(item.key) || SERIES_COLORS[0] }} />
                      <span>{item.label}</span>
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
        <p className={styles.chartNote}>* Bucket marcado como estimado pelo AWS Cost Explorer.</p>
      )}
    </div>
  );
}
