import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

test("Aven form primitives mark native inner controls so the shell owns presentation", () => {
  for (const file of ["input.tsx", "select.tsx", "textarea.tsx", "checkbox.tsx", "radio.tsx"]) {
    assert.match(read("components", "ui", file), /data-aven-control-inner=/, `${file} should mark its native inner control`);
  }

  const compatibility = read("app", "legacy-theme-compat.css");
  assert.match(compatibility, /input\[data-aven-control-inner\]/);
  assert.match(compatibility, /select\[data-aven-control-inner\]/);
  assert.match(compatibility, /textarea\[data-aven-control-inner\]/);
  assert.match(compatibility, /box-shadow:\s*none/);
});

test("FilterBar exposes shared sizing roles instead of stretching every filter", () => {
  const layout = read("components", "aven", "layout.tsx");
  const styles = read("components", "aven", "product-components.module.css");
  const tokens = read("app", "styles", "tokens", "components.css");

  assert.match(layout, /FilterItemSize = "compact" \| "default" \| "wide" \| "fluid"/);
  assert.match(layout, /secondary\?: ReactNode/);
  assert.match(layout, /summary\?: ReactNode/);
  assert.match(styles, /flex:\s*0 1 var\(--filter-field-default-inline-size\)/);
  assert.match(styles, /filterItem\[data-size="fluid"\]/);
  assert.match(styles, /@media \(max-width: 48rem\)/);
  assert.match(tokens, /--filter-field-default-inline-size:\s*calc\(var\(--popover-min-inline-size\) \+ var\(--space-8\)\)/);
  assert.match(tokens, /--filter-field-wide-inline-size:\s*calc\(var\(--filter-field-default-inline-size\) \+ var\(--space-16\)\)/);
});

test("shared multi-select lists remain bounded and scroll internally", () => {
  const styles = read("components", "aven", "product-components.module.css");
  assert.match(styles, /\.selectorOptionList\s*\{[^}]*max-block-size:/s);
  assert.match(styles, /\.selectorOptionList\s*\{[^}]*overflow-y:\s*auto/s);
});

test("dropdown positioning follows trigger size and visual viewport changes", () => {
  const dropdown = read("components", "ui", "dropdown.tsx");
  const positioning = read("components", "ui", "viewport-position.ts");

  assert.match(dropdown, /ResizeObserver/);
  assert.match(dropdown, /window\.visualViewport/);
  assert.match(dropdown, /minInlineSize:\s*position\.minInlineSize/);
  assert.match(positioning, /minInlineSize:\s*trigger\.width/);
  assert.match(positioning, /window\.visualViewport/);
});

test("DateRangePicker keeps native anchored date controls and no custom detached popover", () => {
  const source = read("components", "aven", "date-range-picker.tsx");
  assert.match(source, /type="date"/);
  assert.doesNotMatch(source, /createPortal|position:\s*absolute/);
});
