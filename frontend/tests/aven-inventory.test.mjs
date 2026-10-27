import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  buildInventoryApiQuery,
  parseInventorySearchParams,
  patchInventoryUrl,
} from "../lib/inventory-query.mjs";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Inventory composes the official Aven resource exploration stack", async () => {
  const page = await source("../app/inventory/page.tsx");
  for (const component of [
    "PageHeader",
    "Section",
    "FilterBar",
    "ProviderSelector",
    "AccountSelector",
    "MetricCard",
    "ProviderBadge",
    "ResourceIdentifier",
    "StatusIndicator",
    "DataState",
    "Table",
    "Pagination",
    "Skeleton",
  ]) assert.ok(page.includes(component), `expected ${component} in Inventory`);
  assert.ok(!page.includes("function ProviderBadge"));
  assert.ok(!page.includes("function ResourceIdentifier"));
  assert.ok(!page.includes("function MetricCard"));
});

test("Inventory consumes only persisted query endpoints", async () => {
  const page = await source("../app/inventory/page.tsx");
  assert.ok(page.includes('path: `/inventory/resources?${resourceQuery}`'));
  assert.ok(page.includes('path: "/inventory/options"'));
  assert.ok(page.includes("useApiQuery<InventoryPage>"));
  assert.ok(!page.includes("boto3"));
  assert.ok(!page.includes("oci.core"));
  assert.ok(!page.includes("OciDiscoveryService"));
  assert.ok(!page.includes("AwsInventoryDiscoveryService"));
});

test("Inventory URL state defaults to active resources and preserves server-side controls", () => {
  const state = parseInventorySearchParams(new URLSearchParams(""));
  assert.equal(state.presenceStatus, "active");
  assert.equal(state.sort, "last_seen_at");
  assert.equal(state.direction, "desc");
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 50);

  const query = new URLSearchParams(buildInventoryApiQuery({
    ...state,
    provider: "aws",
    account: "17",
    region: "us-east-1",
    resourceType: "compute_instance",
    lifecycleStatus: "running",
    search: "api",
    page: 2,
  }));
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("account_id"), "17");
  assert.equal(query.get("region"), "us-east-1");
  assert.equal(query.get("resource_type"), "compute_instance");
  assert.equal(query.get("lifecycle_status"), "running");
  assert.equal(query.get("presence_status"), "active");
  assert.equal(query.get("search"), "api");
  assert.equal(query.get("page"), "2");
});

test("Inventory represents All presence in page state without sending an invalid API enum", () => {
  const state = parseInventorySearchParams(new URLSearchParams("presence_status=all"));
  assert.equal(state.presenceStatus, "all");
  const query = new URLSearchParams(buildInventoryApiQuery(state));
  assert.equal(query.has("presence_status"), false);
  assert.match(patchInventoryUrl({ ...state, presenceStatus: "active" }, { presenceStatus: "all" }), /presence_status=all/);
});

test("Inventory exposes server-side sorting, search, pagination and provider/account filters", async () => {
  const page = await source("../app/inventory/page.tsx");
  for (const phrase of [
    "buildInventoryApiQuery",
    "buildInventoryOptionsQuery",
    "SortHeader",
    "onPageChange",
    "Rows per page",
    "label=\"Search\"",
    "label=\"Provider\"",
    "label=\"Account\"",
    "label=\"Region\"",
    "label=\"Resource type\"",
    "label=\"Lifecycle\"",
    "label=\"Presence\"",
  ]) assert.ok(page.includes(phrase), `missing Inventory behavior: ${phrase}`);
});

test("Inventory preserves technical identifiers and independent presence semantics", async () => {
  const page = await source("../app/inventory/page.tsx");
  assert.ok(page.includes("copyValue={resource.resource_id}"));
  assert.ok(page.includes("resource.native_status"));
  assert.ok(page.includes("resource.presence_status"));
  assert.ok(page.includes("Missing resources remain queryable"));
  assert.ok(page.includes("independently from Findings and Opportunities"));
});

test("Inventory route is part of the shared Application Shell navigation", async () => {
  const navigation = await source("../components/app-shell/navigation.ts");
  assert.ok(navigation.includes('{ href: "/inventory", label: "Inventory", icon: Boxes }'));
});

test("Inventory page does not take scroll ownership from Application Shell", async () => {
  const css = await source("../app/inventory/inventory.module.css");
  assert.ok(!css.includes("height: 100vh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
  assert.ok(!css.includes("overflow-x: auto"));
});

test("Inventory files pass the Aven hardcode gate independently", async () => {
  const entries = [
    ["app/inventory/page.tsx", await source("../app/inventory/page.tsx")],
    ["app/inventory/inventory.module.css", await source("../app/inventory/inventory.module.css")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});

test("Inventory is included in normal lint and design-system scopes", async () => {
  const packageJson = await source("../package.json");
  const gate = await source("../scripts/check-design-system.mjs");
  assert.ok(packageJson.includes("--dir app/inventory"));
  assert.ok(gate.includes('path.join(ROOT, "app", "inventory")'));
});

test("Inventory documentation records the functional regression contracts", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_INVENTORY.md", import.meta.url), "utf8");
  for (const phrase of [
    "Persisted Query Boundary",
    "Default Active Scope",
    "Technical Identifiers",
    "Missing Resources",
    "Theme and Hardcode Gate",
  ]) assert.ok(docs.includes(phrase), `missing documentation contract: ${phrase}`);
});
