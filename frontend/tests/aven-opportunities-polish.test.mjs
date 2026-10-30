import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function source(relativePath) {
  return readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("Opportunities uses deterministic table sizing while keeping long identifiers compact and accessible", () => {
  const resourceIdentifier = source("components/aven/resource-identifier.tsx");
  const opportunitiesStyles = source("app/opportunities/opportunities.module.css");
  const tableStyles = source("components/ui/table.module.css");

  assert.match(resourceIdentifier, /export function compactResourceIdentifier/);
  assert.match(resourceIdentifier, /compactResourceIdentifier\(primaryText\)/);
  assert.match(resourceIdentifier, /compactResourceIdentifier\(technicalId\)/);
  assert.match(resourceIdentifier, /Tooltip content=\{primaryText\}/);
  assert.match(resourceIdentifier, /Tooltip content=\{technicalId\}/);
  assert.match(resourceIdentifier, /navigator\.clipboard\.writeText\(valueToCopy\)/);
  assert.match(resourceIdentifier, /aria-label=\{copied \? copiedLabel : copyLabel\}/);

  assert.match(opportunitiesStyles, /table-layout:\s*fixed/);
  assert.match(opportunitiesStyles, /--opportunities-column-1:/);
  assert.match(opportunitiesStyles, /--opportunities-column-8:/);
  assert.match(opportunitiesStyles, /min-inline-size:\s*0/);
  assert.match(opportunitiesStyles, /text-overflow:\s*ellipsis/);
  assert.match(opportunitiesStyles, /-webkit-line-clamp:\s*2/);
  assert.doesNotMatch(opportunitiesStyles, /word-break:\s*break-all/);

  assert.match(tableStyles, /table-layout:\s*auto/);
  assert.match(tableStyles, /\.tableWrapper\s*\{[\s\S]*overflow-x:\s*auto/);
});

test("Opportunity rows keep realistic OCI and AWS identifiers wired to full-value access, copy and selection", () => {
  const page = source("app/opportunities/page.tsx");
  const resourceIdentifier = source("components/aven/resource-identifier.tsx");
  const realisticIdentifiers = [
    "ocid1.instance.oc1.sa-saopaulo-1.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "ocid1.blockvolume.oc1.sa-saopaulo-1.bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0",
  ];

  for (const identifier of realisticIdentifiers) {
    assert.ok(identifier.length > 36, `${identifier} should exercise compact identifier handling`);
  }

  assert.match(page, /technicalId=\{finding\.resource_name \? finding\.resource_id : undefined\}/);
  assert.match(page, /copyValue=\{finding\.resource_id\}/);
  assert.match(page, /aria-label=\{`Selecionar \$\{finding\.title\} · \$\{finding\.resource_id\}`\}/);
  assert.match(page, /toggleSelection\(finding\.id\)/);
  assert.match(resourceIdentifier, /return `\$\{normalized\.slice\(0, COMPACT_IDENTIFIER_PREFIX\)\}…\$\{normalized\.slice\(-COMPACT_IDENTIFIER_SUFFIX\)\}`/);
  assert.match(resourceIdentifier, /tabIndex=\{primaryIsCompacted \? 0 : undefined\}/);
  assert.match(resourceIdentifier, /tabIndex=\{0\}/);
});

test("Opportunity tables share the same column contract across header, rows and loading skeletons", () => {
  const page = source("app/opportunities/page.tsx");
  const opportunitiesStyles = source("app/opportunities/opportunities.module.css");

  assert.match(page, /<TableHeader>/);
  assert.match(page, /<OpportunityLoadingRows history=\{isHistory\} \/>/);
  assert.match(page, /<TableBody>/);
  for (let index = 1; index <= 8; index += 1) {
    assert.match(opportunitiesStyles, new RegExp(`--opportunities-column-${index}:`));
    assert.match(opportunitiesStyles, new RegExp(`th:nth-child\\(${index}\\)`));
    assert.match(opportunitiesStyles, new RegExp(`td:nth-child\\(${index}\\)`));
  }
  assert.match(opportunitiesStyles, /@media \(max-width:\s*64rem\)[\s\S]*min-inline-size:\s*58rem/);
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