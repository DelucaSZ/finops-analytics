import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function source(relativePath) {
  return readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("Opportunities keeps long resource identifiers compact in the decision list", () => {
  const resourceIdentifier = source("components/aven/resource-identifier.tsx");
  const opportunitiesStyles = source("app/opportunities/opportunities.module.css");

  assert.match(resourceIdentifier, /export function compactResourceIdentifier/);
  assert.match(resourceIdentifier, /compactResourceIdentifier\(primaryText\)/);
  assert.match(resourceIdentifier, /compactResourceIdentifier\(technicalId\)/);
  assert.match(resourceIdentifier, /Tooltip content=\{primaryText\}/);
  assert.match(opportunitiesStyles, /table-layout:\s*fixed/);
  assert.doesNotMatch(opportunitiesStyles, /min-(?:inline-)?size:\s*1180px/);
});

test("Opportunities uses a semantic wide Drawer without changing the default Drawer size", () => {
  const drawer = source("components/ui/drawer.tsx");
  const overlays = source("components/ui/overlays.module.css");
  const tokens = source("app/styles/tokens/components.css");
  const detail = source("components/opportunity-detail.tsx");

  assert.match(drawer, /size\?: "default" \| "wide"/);
  assert.match(drawer, /size = "default"/);
  assert.match(detail, /<DrawerContent side="right" size="wide">/);
  assert.match(overlays, /\.drawer\[data-size="wide"\]/);
  assert.match(overlays, /backdrop-filter:\s*var\(--overlay-backdrop-filter\)/);
  assert.match(tokens, /--drawer-inline-size-wide:/);
  assert.match(tokens, /--overlay-backdrop-filter:\s*blur\(var\(--space-1\)\)/);
});

test("Opportunity technical detail retains full cloud identifiers with wrapping and copy feedback", () => {
  const detail = source("components/opportunity-detail.tsx");
  const detailStyles = source("components/opportunity-detail.module.css");

  assert.match(detail, /<dt>ID do recurso<\/dt>/);
  assert.match(detail, /<code>\{detail\.resource_id\}<\/code>/);
  assert.match(detail, /<dt>ID da conta<\/dt>/);
  assert.match(detail, /providerMetadataEntries\.map/);
  assert.match(detail, /copiedTechnicalKey === copyKey \? "Copiado" : "Copiar"/);
  assert.match(detailStyles, /overflow-wrap:\s*anywhere/);
  assert.match(detailStyles, /word-break:\s*break-word/);
  assert.match(detailStyles, /container-type:\s*inline-size/);
  assert.match(detailStyles, /@container \(max-width: 36rem\)/);
});
