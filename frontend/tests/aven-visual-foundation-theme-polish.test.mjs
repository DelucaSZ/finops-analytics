import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TOKENS = path.join(ROOT, "app", "styles", "tokens");

const read = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), "utf8");
const readToken = (name) => fs.readFileSync(path.join(TOKENS, name), "utf8");

function declaration(css, token) {
  const match = css.match(new RegExp(`${token.replaceAll("-", "\\-")}\\s*:\\s*([^;]+);`));
  return match?.[1]?.trim() ?? null;
}

function ruleBlock(css, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`))?.[1] ?? "";
}

test("Task 24.20 maps the application canvas to the official Aven gradients", () => {
  const light = readToken("semantic-light.css");
  const dark = readToken("semantic-dark.css");

  assert.equal(declaration(light, "--application-background"), "var(--gradient-background-light)");
  assert.equal(declaration(dark, "--application-background"), "var(--gradient-background-dark)");
  assert.equal(declaration(light, "--page-background"), "transparent");
  assert.equal(declaration(dark, "--page-background"), "transparent");
  assert.equal(declaration(dark, "--surface-elevated"), "var(--aven-color-neutral-800)");
});

test("canonical tokens remain before transitional CSS while the post-compatibility bridge restores Aven semantics", () => {
  const layout = read("app/layout.tsx");
  const compat = read("app/legacy-theme-compat.css");

  const tokenIndex = layout.indexOf('import "./styles/tokens/index.css"');
  const uiSystemIndex = layout.indexOf('import "./ui-system.css"');
  const compatIndex = layout.indexOf('import "./legacy-theme-compat.css"');

  assert.ok(tokenIndex >= 0 && uiSystemIndex > tokenIndex, "Aven tokens must remain available before transitional UI CSS");
  assert.ok(compatIndex > uiSystemIndex, "semantic compatibility bridge must load after transitional UI CSS");
  assert.match(compat, /html\[data-theme="light"\]/);
  assert.match(compat, /html\[data-theme="dark"\]/);

  assert.equal(declaration(compat, "--background"), "var(--application-background)");
  assert.equal(declaration(compat, "--surface"), "var(--surface-primary)");
  assert.equal(declaration(compat, "--primary"), "var(--action-primary)");
  assert.equal(declaration(compat, "--radius-lg"), "var(--radius-card)");
  assert.equal(declaration(compat, "--shadow"), "var(--shadow-sm)");
});

test("ApplicationShell exposes the shared canvas and removes the full-width topbar separator", () => {
  const styles = read("components/app-shell/app-shell.module.css");
  const components = readToken("components.css");

  assert.equal(declaration(components, "--shell-background"), "var(--application-background)");
  assert.equal(declaration(components, "--shell-content-background"), "var(--page-background)");
  assert.equal(declaration(components, "--sidebar-background"), "var(--surface-overlay)");
  assert.equal(declaration(components, "--topbar-background"), "var(--header-background)");

  assert.match(ruleBlock(styles, ".shell"), /background:\s*var\(--shell-background\)/);
  assert.match(ruleBlock(styles, ".mainContent"), /background:\s*var\(--shell-content-background\)/);
  assert.match(ruleBlock(styles, ".bootScreen"), /background:\s*var\(--shell-background\)/);
  assert.doesNotMatch(ruleBlock(styles, ".topbar"), /border-block-end/);
});

test("card and overlay hierarchy continues to resolve through shared elevation roles", () => {
  const components = readToken("components.css");

  assert.equal(declaration(components, "--card-background"), "var(--elevation-1-surface)");
  assert.equal(declaration(components, "--card-border"), "var(--elevation-1-border)");
  assert.equal(declaration(components, "--card-shadow"), "var(--elevation-1-shadow)");
  assert.equal(declaration(components, "--popover-background"), "var(--elevation-2-surface)");
  assert.equal(declaration(components, "--dialog-background"), "var(--elevation-3-surface)");
});
