import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

function* sourceFiles(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) yield* sourceFiles(absolute);
    else if (entry.name.endsWith(".tsx")) yield absolute;
  }
}

test("Aven single-select replaces the browser popup while retaining the native form value contract", () => {
  const select = read("components", "ui", "select.tsx");
  assert.match(select, /export const Select = forwardRef<HTMLSelectElement/);
  assert.match(select, /export const NativeSelect = forwardRef/);
  assert.match(select, /data-aven-control-inner/);
  assert.match(select, /data-aven-native-select/);
  assert.match(select, /setRef\(forwardedRef, node\)/);
  assert.match(select, /name=\{name\}/);
  assert.match(select, /required=\{required\}/);
  assert.match(select, /onChange=\{onChange\}/);
  assert.match(select, /dispatchEvent\(new Event\("change", \{ bubbles: true \}\)\)/);
  assert.match(select, /value=\{value\}/);
  assert.match(select, /defaultValue=\{defaultValue\}/);
});

test("select popover supports viewport positioning, dialogs and keyboard/assistive semantics", () => {
  const select = read("components", "ui", "select.tsx");
  const dropdown = read("components", "ui", "dropdown.tsx");
  const styles = read("components", "ui", "primitives.module.css");
  for (const token of [
    'role="combobox"', 'role="listbox"', 'role="option"', "aria-selected=",
    "aria-activedescendant=", "aria-expanded=", "aria-controls=",
    '"ArrowDown"', '"ArrowUp"', '"Home"', '"End"', '"Escape"',
    'event.key === "Enter"', "createPortal(", "ResizeObserver",
    'window.addEventListener("scroll", update, true)', "positionDropdown(",
    'closest("dialog[open]")', "onBlur=",
  ]) assert.ok(select.includes(token), "Missing selection contract: " + token);
  assert.match(dropdown, /closest\("dialog\[open\]"\)/);
  assert.match(styles, /\.selectPopover\s*\{[^}]*max-block-size:[^}]*overflow-y:\s*auto/s);
  assert.match(styles, /\.selectShell\[data-open="true"\]/);
  assert.match(styles, /\.selectOption\[aria-selected="true"\]/);
  assert.match(styles, /var\(--popover-background\)/);
  assert.match(styles, /var\(--popover-shadow\)/);
});

test("all page and product dropdowns use the shared selection primitives", () => {
  for (const group of ["app", "components"]) {
    for (const absolute of sourceFiles(path.join(ROOT, group))) {
      if (absolute.endsWith(path.join("ui", "select.tsx"))) continue;
      const text = fs.readFileSync(absolute, "utf8");
      assert.doesNotMatch(
        text,
        /<select(?=\s|>)/,
        "A native browser popup remains in " + path.relative(ROOT, absolute),
      );
    }
  }
});

test("native compatibility migrations retain source options and changes without altering filter logic", () => {
  for (const page of [
    "app/settings/accounts/page.tsx",
    "app/settings/usage-costs/page.tsx",
    "app/settings/audit/page.tsx",
    "app/settings/pricing/oci/page.tsx",
    "app/settings/users/page.tsx",
    "app/settings/https/page.tsx",
    "app/collections/[collectionId]/compare/page.tsx",
    "components/collection-workspace.tsx",
  ]) {
    const text = read(...page.split("/"));
    assert.match(text, /<NativeSelect[\s>]/, "Missing adapter in " + page);
    assert.match(text, /onChange=/, "Missing preserved consumer callback in " + page);
    assert.match(text, /<option[\s>]/, "Missing preserved options in " + page);
  }
  const selectors = read("components", "aven", "selectors.tsx");
  assert.match(selectors, /<DropdownMenu/);
  assert.match(selectors, /<Checkbox/);
  assert.match(selectors, /selection\.multiple/);
  const billing = read("app", "billing", "page.tsx");
  assert.match(billing, /<AccountSelector/);
  assert.match(billing, /<Select/);
});
