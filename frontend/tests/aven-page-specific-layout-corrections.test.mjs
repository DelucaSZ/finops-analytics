import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

function rule(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`));
  assert.ok(match, `missing rule: ${selector}`);
  return match[1];
}

test("Collections keeps filter behavior while using official form controls", () => {
  const source = read("components", "collection-workspace.tsx");

  for (const label of [
    "Cloud",
    "Conta · nome ou identificador",
    "Status",
    "Início do período (inclusivo)",
    "Fim do período (exclusivo)",
    "Versão dos analyzers",
  ]) {
    assert.match(source, new RegExp(`label=\\"${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\"`));
  }

  assert.match(source, /import \{ Button, Input, Select \} from "@\/components\/ui"/);
  assert.match(source, /event\.preventDefault\(\)/);
  assert.match(source, /new Date\(draft\.date_from\) >= new Date\(draft\.date_to\)/);
  assert.match(source, /change\(\{ \.\.\.draft, page: 1 \}\)/);
  assert.match(source, /<Button type="submit">Aplicar filtros<\/Button>/);
});

test("Collections neutralizes the legacy Opportunities field shell instead of stacking borders", () => {
  const styles = read("app", "collections", "collections-layout.module.css");
  const fieldShell = rule(styles, '.scope :global(.opportunity-filter > div)');
  const focusShell = rule(styles, '.scope :global(.opportunity-filter > div:focus-within)');

  assert.match(fieldShell, /background:\s*transparent/);
  assert.match(fieldShell, /border:\s*0/);
  assert.match(fieldShell, /box-shadow:\s*none/);
  assert.match(fieldShell, /display:\s*grid/);
  assert.match(fieldShell, /gap:\s*var\(--form-field-gap\)/);
  assert.match(fieldShell, /padding:\s*var\(--space-0\)/);
  assert.match(focusShell, /box-shadow:\s*none/);
});

test("Collections filter layout is compact, adaptive and consumes extra shell width", () => {
  const styles = read("app", "collections", "collections-layout.module.css");
  const panel = rule(styles, '.scope :global(.opportunity-filter-panel)');
  const heading = rule(styles, '.scope :global(.opportunity-filter-heading)');
  const grid = rule(styles, '.scope :global(.opportunity-filter-grid)');
  const account = rule(styles, '.scope :global(.opportunity-filter.account-filter)');
  const actions = rule(styles, '.scope :global(.opportunity-filter-panel > .collection-toolbar)');
  const summary = rule(styles, '.scope :global(.active-filter-summary)');

  assert.match(panel, /gap:\s*var\(--space-3\)/);
  assert.match(panel, /padding:\s*var\(--space-4\)/);
  assert.match(heading, /border-block-end:\s*0/);
  assert.match(heading, /padding:\s*var\(--space-0\)/);
  assert.match(grid, /display:\s*grid/);
  assert.match(grid, /auto-fit/);
  assert.match(grid, /--filter-field-min-inline-size/);
  assert.match(grid, /padding:\s*var\(--space-0\)/);
  assert.match(account, /grid-column:\s*span 2/);
  assert.match(actions, /justify-content:\s*flex-start/);
  assert.match(summary, /padding:\s*var\(--space-0\)/);
  assert.match(styles, /@media \(max-width: 48rem\)[\s\S]*opportunity-filter\.account-filter[\s\S]*grid-column:\s*span 1/);
});

test("Collections page-specific filter corrections use semantic Aven tokens", () => {
  const styles = read("app", "collections", "collections-layout.module.css");
  const filterSection = styles.slice(
    styles.indexOf('.scope :global(.opportunity-filter-panel)'),
    styles.indexOf('.scope :global(.collection-toolbar select)'),
  );

  assert.ok(filterSection.length > 0);
  assert.doesNotMatch(filterSection, /#[0-9a-f]{3,8}\b/i);
  assert.doesNotMatch(filterSection, /rgba?\(/i);
  assert.match(filterSection, /var\(--space-/);
  assert.match(filterSection, /var\(--filter-grid-gap\)/);
  assert.match(filterSection, /var\(--form-field-gap\)/);
});
