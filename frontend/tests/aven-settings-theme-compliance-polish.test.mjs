import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Policies no longer renders dark-only legacy segmented controls or switches", async () => {
  const page = await source("../app/settings/policies/page.tsx");

  for (const primitive of [
    "PageHeader",
    "Alert",
    "Badge",
    "Button",
    "Card",
    "Checkbox",
    "EmptyState",
    "Input",
    "Select",
    "Switch",
    "Textarea",
  ]) {
    assert.ok(page.includes(primitive), `expected ${primitive} in Policies`);
  }

  assert.ok(page.includes("SegmentedButtons"));
  assert.ok(page.includes('role="group"'));
  assert.ok(page.includes("aria-pressed={selected}"));
  assert.ok(page.includes('variant={selected ? "secondary" : "ghost"}'));
  assert.equal(page.includes('className="segmented"'), false);
  assert.equal(page.includes('className="switch"'), false);
  assert.equal(page.includes('className="button primary"'), false);
  assert.equal(page.includes('className="alert error"'), false);
});

test("Policies visual layer is semantic-token only and preserves responsive overflow safety", async () => {
  const [page, css] = await Promise.all([
    source("../app/settings/policies/page.tsx"),
    source("../app/settings/policies/page.module.css"),
  ]);

  const violations = [
    ...scanText(page, "app/settings/policies/page.tsx"),
    ...scanText(css, "app/settings/policies/page.module.css"),
  ];
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);

  assert.ok(css.includes("var(--surface-secondary)"));
  assert.ok(css.includes("var(--border-subtle)"));
  assert.ok(css.includes("var(--control-radius)"));
  assert.ok(css.includes("var(--status-neutral-bg)"));
  assert.ok(css.includes("overflow-wrap: anywhere"));
  assert.ok(css.includes("minmax(0, 1fr)"));
  assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b/i);
  assert.doesNotMatch(css, /rgba?\(/i);
});

test("Opportunity policy uses official Aven controls and keeps persistence behavior", async () => {
  const [page, css] = await Promise.all([
    source("../app/settings/opportunities/page.tsx"),
    source("../app/settings/opportunities/page.module.css"),
  ]);

  for (const primitive of ["PageHeader", "Section", "Alert", "Button", "Card", "Input", "Select", "Switch"]) {
    assert.ok(page.includes(primitive), `expected ${primitive} in Opportunity settings`);
  }

  for (const contract of [
    'api<OpportunityPolicy>("/settings/opportunity-policy")',
    'api<Preview>("/settings/opportunity-policy/preview"',
    'method: "POST"',
    'method: "PUT"',
    "expected_version: policy.version",
  ]) {
    assert.ok(page.includes(contract), `missing Opportunity settings contract ${contract}`);
  }

  assert.equal(page.includes('className="switch"'), false);
  assert.equal(page.includes('className="button primary"'), false);
  assert.equal(page.includes('className="alert error"'), false);
  assert.equal(page.includes('className={`panel'), false);

  const violations = [
    ...scanText(page, "app/settings/opportunities/page.tsx"),
    ...scanText(css, "app/settings/opportunities/page.module.css"),
  ];
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
  assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b/i);
  assert.doesNotMatch(css, /rgba?\(/i);
});

test("Settings compatibility bridge resolves legacy administrative surfaces through Aven semantics", async () => {
  const css = await source("../app/settings/settings-layout.module.css");

  assert.ok(css.includes("Legacy segmented controls"));
  assert.ok(css.includes("Legacy switch bridge"));
  assert.ok(css.includes("var(--surface-selected)"));
  assert.ok(css.includes("var(--state-selected-border)"));
  assert.ok(css.includes("var(--border-interactive)"));
  assert.ok(css.includes("var(--surface-disabled)"));
  assert.ok(css.includes("var(--action-primary)"));
  assert.ok(css.includes("var(--action-primary-text)"));
  assert.ok(css.includes("var(--action-secondary)"));
  assert.ok(css.includes("var(--status-danger-bg)"));
  assert.ok(css.includes("var(--status-success-bg)"));
  assert.ok(css.includes("var(--status-warning-bg)"));
  assert.ok(css.includes("var(--status-info-bg)"));
  assert.ok(css.includes("var(--status-neutral-bg)"));
  assert.ok(css.includes("select:not([data-aven-control-inner]) option"));
  assert.ok(css.includes("var(--popover-background)"));
  assert.ok(css.includes("max-inline-size: calc(var(--filter-field-wide-inline-size)"));
  assert.ok(css.includes(":global(.settings-filters)"));
  assert.ok(css.includes(":global(.account-card)"));
  assert.ok(css.includes(":global(.data-table th)"));
  assert.doesNotMatch(css, /--state-hover-border/);
  assert.doesNotMatch(css, /background:\s*(?:black|#000(?:000)?)/i);
  assert.doesNotMatch(css, /filter:\s*invert\(/i);
});

test("Settings compatibility bridge only consumes defined Aven token roles", async () => {
  const [css, ...tokenFiles] = await Promise.all([
    source("../app/settings/settings-layout.module.css"),
    source("../app/styles/tokens/primitives.css"),
    source("../app/styles/tokens/foundations.css"),
    source("../app/styles/tokens/semantic-light.css"),
    source("../app/styles/tokens/semantic-dark.css"),
    source("../app/styles/tokens/components.css"),
    source("../app/styles/tokens/status.css"),
  ]);

  const defined = new Set(
    tokenFiles.flatMap((text) => [...text.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map((match) => match[1])),
  );
  const used = new Set([...css.matchAll(/var\((--[a-z0-9-]+)/gi)].map((match) => match[1]));
  const missing = [...used].filter((token) => !defined.has(token)).sort();
  assert.deepEqual(missing, [], `undefined Aven tokens in Settings bridge: ${missing.join(", ")}`);
});

test("remaining Accounts and Users legacy markup is explicitly covered by the semantic migration bridge", async () => {
  const [accounts, users, css] = await Promise.all([
    source("../app/settings/accounts/page.tsx"),
    source("../app/settings/users/page.tsx"),
    source("../app/settings/settings-layout.module.css"),
  ]);

  assert.match(accounts, /className="[^"]*\bsegmented\b[^"]*"/);
  assert.ok(accounts.includes("account-card"));
  assert.ok(css.includes(":global(.segmented button.active)"));
  assert.ok(css.includes(":global(.account-card)"));

  assert.ok(users.includes("settings-filters"));
  assert.ok(users.includes("settings-row-actions"));
  assert.ok(css.includes(":global(.settings-filters)"));
  assert.ok(css.includes(":global(.settings-row-actions)"));
  assert.ok(css.includes(":global(.form-error)"));
  assert.ok(css.includes(":global(.form-success)"));
});

test("Appearance continues to delegate Light Dark System behavior to the official ThemeSelector", async () => {
  const page = await source("../app/settings/appearance/page.tsx");
  assert.ok(page.includes("<ThemeSelector"));
  assert.ok(page.includes('from "@/components/theme-selector"'));
  assert.equal(page.includes("localStorage"), false);
  assert.equal(page.includes("matchMedia"), false);
  assert.equal(page.includes("data-theme"), false);
});

test("Policies keeps the existing functional API contracts", async () => {
  const page = await source("../app/settings/policies/page.tsx");
  for (const contract of [
    "/cloud-accounts",
    "/cloud-accounts/capabilities",
    "/auth/me",
    "/policies/global",
    "/policies/accounts/",
    'method: "PUT"',
    'method: "DELETE"',
  ]) {
    assert.ok(page.includes(contract), `missing Policies contract ${contract}`);
  }
  assert.ok(page.includes("canManagePolicies"));
  assert.ok(page.includes("override_fields"));
});

test("frontend lint scope covers both Settings policy surfaces migrated in this task", async () => {
  const packageJson = await source("../package.json");
  assert.ok(packageJson.includes("--file app/settings/policies/page.tsx"));
  assert.ok(packageJson.includes("--file app/settings/opportunities/page.tsx"));
});
