import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, scanText, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const UI = path.join(ROOT, "components", "ui");
const read = (name) => fs.readFileSync(path.join(UI, name), "utf8");

const requiredFiles = [
  "button.tsx", "icon-button.tsx", "input.tsx", "textarea.tsx", "select.tsx", "checkbox.tsx",
  "radio.tsx", "switch.tsx", "badge.tsx", "tooltip.tsx", "dropdown.tsx", "tabs.tsx", "dialog.tsx",
  "drawer.tsx", "card.tsx", "table.tsx", "pagination.tsx", "skeleton.tsx", "alert.tsx", "empty-state.tsx",
  "toast.tsx", "divider.tsx", "avatar.tsx", "spinner.tsx", "index.ts", "primitives.module.css", "overlays.module.css", "feedback.module.css",
];

test("Aven UI exports every required primitive", () => {
  for (const file of requiredFiles) assert.ok(fs.existsSync(path.join(UI, file)), `${file} should exist`);
  const barrel = read("index.ts");
  for (const file of requiredFiles.filter((file) => file.endsWith(".tsx"))) {
    const stem = file.replace(/\.tsx$/, "");
    assert.match(barrel, new RegExp(`\\./${stem}`), `${stem} should be barrel-exported`);
  }
});

test("hardcode gate is zero for components/ui", () => {
  const summary = summarize(scanDirectory(UI));
  assert.deepEqual(summary, { colors: 0, spacing: 0, radius: 0, typography: 0 });
});

test("hardcode scanner rejects representative forbidden values", () => {
  const source = `.bad { color: #fff; padding: 16px; border-radius: 10px; font-size: 14px; }`;
  const summary = summarize(scanText(source, "fixture.css"));
  assert.deepEqual(summary, { colors: 1, spacing: 1, radius: 1, typography: 1 });
});

test("Button exposes semantic variants and loading semantics", () => {
  const source = read("button.tsx");
  for (const variant of ["primary", "secondary", "outline", "ghost", "danger"]) assert.match(source, new RegExp(`"${variant}"`));
  assert.match(source, /aria-busy=/);
  assert.match(source, /disabled=\{disabled \|\| loading\}/);
  assert.match(source, /<Spinner/);
});

test("form primitives expose native semantics and accessible error state", () => {
  assert.match(read("input.tsx"), /<input/);
  assert.match(read("input.tsx"), /aria-invalid=/);
  assert.match(read("textarea.tsx"), /<textarea/);
  assert.match(read("select.tsx"), /<select/);
  assert.match(read("checkbox.tsx"), /type="checkbox"/);
  assert.match(read("checkbox.tsx"), /indeterminate/);
  assert.match(read("radio.tsx"), /type="radio"/);
  assert.match(read("switch.tsx"), /role="switch"/);
  assert.match(read("switch.tsx"), /aria-checked=/);
});

test("Tabs and Dropdown implement keyboard navigation", () => {
  const tabs = read("tabs.tsx");
  const dropdown = read("dropdown.tsx");
  for (const key of ["ArrowRight", "ArrowLeft", "Home", "End"]) assert.match(tabs, new RegExp(key));
  for (const key of ["ArrowDown", "ArrowUp", "Home", "End", "Escape"]) assert.match(dropdown, new RegExp(key));
  assert.match(dropdown, /role="menu"/);
  assert.match(dropdown, /role="menuitem"/);
});

test("Dialog and Drawer use native modal behavior with Escape/cancel handling", () => {
  for (const file of ["dialog.tsx", "drawer.tsx"]) {
    const source = read(file);
    assert.match(source, /<dialog/);
    assert.match(source, /showModal\(\)/);
    assert.match(source, /onCancel=/);
    assert.match(source, /aria-labelledby=/);
    assert.match(source, /aria-describedby=/);
  }
});

test("overlay primitives preserve accessible portal behavior", () => {
  const tooltip = read("tooltip.tsx");
  const dropdown = read("dropdown.tsx");
  const toast = read("toast.tsx");
  assert.match(tooltip, /createPortal/);
  assert.match(tooltip, /aria-describedby/);
  assert.match(dropdown, /createPortal/);
  assert.match(dropdown, /aria-labelledby=/);
  assert.match(toast, /createPortal/);
  assert.match(toast, /onFocusCapture=/);
});

test("Switch associates label and description with the native button", () => {
  const source = read("switch.tsx");
  assert.match(source, /aria-labelledby=/);
  assert.match(source, /aria-describedby=/);
  assert.match(source, /htmlFor=\{controlId\}/);
});

test("animated primitives include reduced-motion handling and avoid transition all", () => {
  const css = ["primitives.module.css", "overlays.module.css", "feedback.module.css"]
    .map((file) => read(file))
    .join("\n");
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.doesNotMatch(css, /transition\s*:\s*all/i);
  assert.doesNotMatch(css, /transition-property\s*:\s*all/i);
});
