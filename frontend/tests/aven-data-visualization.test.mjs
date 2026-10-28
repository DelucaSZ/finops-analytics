import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("Aven visualization tokens expose categorical and semantic chart roles in light and dark themes", () => {
  const source = read("app/styles/tokens/visualization.css");

  for (let index = 1; index <= 6; index += 1) {
    const token = `--chart-series-${index}`;
    assert.equal(source.split(token).length - 1, 2, `${token} must be defined for light and dark themes`);
  }

  for (const token of [
    "--chart-grid",
    "--chart-axis",
    "--chart-label",
    "--chart-tooltip-bg",
    "--chart-tooltip-text",
    "--chart-reference-line",
    "--chart-forecast",
    "--chart-estimated",
    "--chart-comparison",
    "--chart-baseline",
  ]) {
    assert.equal(source.split(token).length - 1, 2, `${token} must be defined for light and dark themes`);
  }
});

test("chart consumers use Aven visualization tokens instead of legacy chart color aliases", () => {
  const billing = read("app/billing/billing-cost-chart.tsx");
  const flow = read("app/flow/flow-layout.module.css");
  const dashboard = read("components/executive-dashboard.module.css");
  const usageCosts = read("app/settings/usage-costs/usage-costs.module.css");

  assert.match(billing, /var\(--chart-series-1\)/);
  assert.match(billing, /var\(--chart-forecast\)/);
  assert.match(flow, /var\(--chart-axis\)/);
  assert.match(flow, /var\(--chart-series-1\)/);
  assert.match(flow, /var\(--chart-series-2\)/);
  assert.match(flow, /var\(--chart-series-3\)/);
  assert.match(dashboard, /var\(--chart-series-1\)/);
  assert.match(usageCosts, /var\(--chart-axis\)/);
  assert.match(usageCosts, /var\(--chart-label\)/);
  assert.match(usageCosts, /var\(--chart-series-1\)/);
  assert.doesNotMatch(usageCosts, /var\(--chart-1\)/);
});

test("ChartCard remains the canonical stateful container for chart surfaces", () => {
  const source = read("components/aven/layout.tsx");

  assert.match(source, /export interface ChartCardProps/);
  assert.match(source, /loading\?: boolean/);
  assert.match(source, /error\?: ReactNode/);
  assert.match(source, /empty\?: boolean/);
  assert.match(source, /<DataState/);
});

test("visualization palette stays provider-neutral", () => {
  const source = read("app/styles/tokens/visualization.css").toLowerCase();

  assert.doesNotMatch(source, /aws/);
  assert.doesNotMatch(source, /oci/);
  assert.match(source, /categorical, not provider identities/);
});
