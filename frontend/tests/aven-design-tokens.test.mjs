import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const appUrl = new URL("../app/", import.meta.url);
const tokensUrl = new URL("styles/tokens/", appUrl);

async function readTokenFile(name) {
  return readFile(new URL(name, tokensUrl), "utf8");
}

function declaredTokens(css) {
  return [...css.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map((match) => match[1]);
}

function assertNoDuplicateDeclarations(css, fileName) {
  const names = declaredTokens(css);
  const duplicates = names.filter((name, index) => names.indexOf(name) !== index);
  assert.deepEqual([...new Set(duplicates)], [], `${fileName} contains duplicate token declarations`);
}

test("Aven token runtime is loaded before the transitional UI compatibility layer", async () => {
  const layout = await readFile(new URL("layout.tsx", appUrl), "utf8");
  const tokenImport = layout.indexOf('import "./styles/tokens/index.css";');
  const uiSystemImport = layout.indexOf('import "./ui-system.css";');

  assert.ok(tokenImport >= 0, "layout must load the Aven token runtime");
  assert.ok(uiSystemImport >= 0, "layout must keep the existing UI system during migration");
  assert.ok(tokenImport < uiSystemImport, "Aven tokens must be available before transitional UI CSS");
});

test("Aven token layers expose the essential semantic contract", async () => {
  const [primitives, light, dark, status, visualization, components, legacy, index] = await Promise.all([
    readTokenFile("primitives.css"),
    readTokenFile("semantic-light.css"),
    readTokenFile("semantic-dark.css"),
    readTokenFile("status.css"),
    readTokenFile("visualization.css"),
    readTokenFile("components.css"),
    readTokenFile("legacy.css"),
    readTokenFile("index.css"),
  ]);

  for (const requiredImport of [
    "primitives.css",
    "semantic-light.css",
    "semantic-dark.css",
    "status.css",
    "visualization.css",
    "components.css",
    "legacy.css",
  ]) {
    assert.match(index, new RegExp(requiredImport.replace(".", "\\.")));
  }

  for (const token of [
    "--aven-color-blue-500",
    "--aven-color-indigo-500",
    "--aven-color-violet-500",
    "--aven-color-neutral-950",
    "--gradient-brand",
    "--space-6",
    "--radius-control",
    "--radius-card",
    "--font-family-ui",
    "--font-weight-semibold",
    "--font-size-sm",
    "--shadow-md",
  ]) {
    assert.ok(primitives.includes(`${token}:`), `missing primitive ${token}`);
  }

  for (const semantic of [
    "--background-primary",
    "--surface-primary",
    "--surface-elevated",
    "--text-primary",
    "--text-secondary",
    "--text-muted",
    "--border-subtle",
    "--border-focus",
    "--action-primary",
    "--action-primary-hover",
    "--action-disabled",
    "--focus-ring",
    "--state-selected-bg",
    "--overlay-backdrop",
  ]) {
    assert.ok(light.includes(`${semantic}:`), `light theme is missing ${semantic}`);
    assert.ok(dark.includes(`${semantic}:`), `dark theme is missing ${semantic}`);
  }

  for (const family of ["success", "warning", "danger", "info", "neutral"]) {
    for (const suffix of ["", "-bg", "-border", "-text"]) {
      assert.ok(status.includes(`--status-${family}${suffix}:`), `missing status token ${family}${suffix}`);
    }
  }

  for (let series = 1; series <= 6; series += 1) {
    assert.ok(visualization.includes(`--chart-series-${series}:`), `missing chart series ${series}`);
  }

  for (const token of ["--chart-grid", "--chart-tooltip-bg", "--chart-forecast", "--chart-estimated"]) {
    assert.ok(visualization.includes(`${token}:`), `missing visualization token ${token}`);
  }

  assert.ok(components.includes("--sidebar-background: var(--surface-primary);"));
  assert.ok(components.includes("--card-border: var(--border-subtle);"));
  assert.ok(legacy.includes("--aven-blue: var(--aven-color-blue-500);"));
});

test("token definition files do not contain accidental duplicate declarations within a layer", async () => {
  for (const fileName of ["primitives.css", "semantic-light.css", "semantic-dark.css", "components.css", "legacy.css"]) {
    assertNoDuplicateDeclarations(await readTokenFile(fileName), fileName);
  }
});

test("new Aven semantic/component layers do not expose page-specific token names", async () => {
  const [light, dark, status, visualization, components] = await Promise.all([
    readTokenFile("semantic-light.css"),
    readTokenFile("semantic-dark.css"),
    readTokenFile("status.css"),
    readTokenFile("visualization.css"),
    readTokenFile("components.css"),
  ]);
  const contract = [light, dark, status, visualization, components].join("\n");

  for (const forbiddenPrefix of ["--billing-", "--dashboard-", "--reservation-", "--opportunities-", "--flow-"]) {
    assert.doesNotMatch(contract, new RegExp(forbiddenPrefix));
  }
});
