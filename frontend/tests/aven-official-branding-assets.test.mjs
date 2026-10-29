import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BRAND_DIR = path.join(ROOT, "public", "brand", "aven");
const read = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), "utf8");

const officialAssets = [
  "aven-logo-horizontal-on-dark.png",
  "aven-logo-horizontal-on-light.png",
  "aven-logo-vertical-on-dark.png",
  "aven-logo-vertical-on-light.png",
  "aven-mark-gradient.png",
  "favicon.ico",
  "apple-touch-icon.png",
];

test("official Aven Brand Kit production assets are versioned under one frontend brand directory", () => {
  for (const asset of officialAssets) {
    const file = path.join(BRAND_DIR, asset);
    assert.ok(fs.existsSync(file), `${asset} should exist`);
    assert.ok(fs.statSync(file).size > 0, `${asset} should not be empty`);
  }
});

test("AvenLogo centralizes horizontal, vertical, mark and surface-aware official asset selection", () => {
  const component = read("components/brand/brand-logo.tsx");
  const config = read("lib/brand.ts");

  assert.match(component, /export type AvenLogoVariant = "horizontal" \| "vertical" \| "mark"/);
  assert.match(component, /export type AvenLogoSurface = "light" \| "dark"/);
  assert.match(component, /surfaceKey = surface === "dark" \? "onDark" : "onLight"/);
  assert.match(component, /brand\.assets\.logo\[variant\]\[surfaceKey\]/);
  assert.match(component, /brand\.assets\.mark\.gradient/);
  assert.match(component, /from "next\/image"/);
  assert.match(config, /wordmarkFallback:[\s\S]*aven-logo-horizontal-fallback\.svg/);
});

test("Login renders the official vertical lockup with its integrated tagline rather than textual logo reconstruction", () => {
  const auth = read("components/auth/auth-layout.tsx");
  assert.match(auth, /<AvenLogo[\s\S]*variant="vertical"[\s\S]*surface=\{surface\}[\s\S]*priority/);
  assert.doesNotMatch(auth, />\s*AVEN\s*</i);
  assert.doesNotMatch(auth, /PRODUCT_TAGLINE/);
  assert.doesNotMatch(auth, /aven-logo-horizontal-fallback\.svg/);
});

test("Sidebar keeps central branding, expanded wordmark and collapsed mark without direct asset paths", () => {
  const shell = read("components/app-shell/application-shell.tsx");
  assert.match(shell, /<BrandLogo variant="wordmark" decorative \/>/);
  assert.match(shell, /<BrandLogo variant="symbol" decorative \/>/);
  assert.doesNotMatch(shell, /\/brand\/aven\//);
  assert.doesNotMatch(shell, />\s*AVEN\s*</i);
});

test("primary branding does not use CSS transforms to manufacture light or dark variants", () => {
  const brandStyles = read("components/brand/brand-logo.module.css");
  const shellStyles = read("components/app-shell/app-shell.module.css");
  const authStyles = read("components/auth/auth-layout.module.css");
  const source = `${brandStyles}\n${shellStyles}\n${authStyles}`;
  assert.doesNotMatch(source, /filter:\s*(?:invert|brightness)\(/);
  assert.doesNotMatch(source, /mix-blend-mode:/);
});

test("root metadata uses official favicon and Apple touch assets without the SVG symbol fallback", () => {
  const layout = read("app/layout.tsx");
  assert.match(layout, /brand\.assets\.icons\.favicon/);
  assert.match(layout, /brand\.assets\.icons\.appleTouch/);
  assert.doesNotMatch(layout, /symbolGradient/);
});
