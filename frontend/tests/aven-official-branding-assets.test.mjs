import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BRAND_DIR = path.join(ROOT, "public", "brand", "aven");
const read = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), "utf8");

const fullHdLogoAssets = [
  "aven_logo_horizontal_dark_ui_4096.svg",
  "aven_logo_horizontal_light_ui_4096.svg",
  "aven_logo_horizontal_no_tagline_dark_ui_4096.svg",
  "aven_logo_horizontal_no_tagline_light_ui_4096.svg",
  "aven_logo_vertical_dark_ui_4096.svg",
  "aven_logo_vertical_light_ui_4096.svg",
  "aven_logo_vertical_no_tagline_dark_text_4096.svg",
  "aven_logo_vertical_no_tagline_white_text_4096.svg",
];

const legacyRasterAssets = [
  "aven-logo-horizontal-on-dark.png",
  "aven-logo-horizontal-on-light.png",
  "aven-logo-vertical-on-dark.png",
  "aven-logo-vertical-on-light.png",
  "aven-mark-gradient.png",
];

test("Aven Full HD production lockups are versioned as official vector masters under the frontend brand directory", () => {
  for (const asset of fullHdLogoAssets) {
    const file = path.join(BRAND_DIR, asset);
    assert.ok(fs.existsSync(file), `${asset} should exist`);
    assert.ok(fs.statSync(file).size > 0, `${asset} should not be empty`);
    const source = fs.readFileSync(file, "utf8");
    assert.match(source, /^<svg\b/);
    assert.match(source, /viewBox="0 0 (?:1600 625|1200 1200)"/);
  }

  for (const asset of legacyRasterAssets) {
    assert.equal(fs.existsSync(path.join(BRAND_DIR, asset)), false, `${asset} should be removed`);
  }
});

test("technical wordmark fallback contains the refreshed official artwork rather than the legacy approximation", () => {
  const fallback = fs.readFileSync(path.join(BRAND_DIR, "aven-logo-horizontal-fallback.svg"), "utf8");
  const official = fs.readFileSync(path.join(BRAND_DIR, "aven_logo_horizontal_no_tagline_light_ui_4096.svg"), "utf8");
  assert.equal(fallback, official);
});

test("AvenLogo centralizes Full HD lockup selection and theme-aware surfaces", () => {
  const component = read("components/brand/brand-logo.tsx");
  const config = read("lib/brand.ts");

  assert.match(component, /export type AvenLogoVariant = "horizontal" \| "horizontalNoTagline" \| "vertical" \| "verticalNoTagline" \| "mark"/);
  assert.match(component, /surfaceKey = surface === "dark" \? "onDark" : "onLight"/);
  assert.match(component, /if \(variant === "wordmark"\) return "horizontalNoTagline"/);
  assert.match(component, /if \(variant === "symbol"\) return "horizontal"/);
  assert.match(component, /brand\.assets\.logo\[variant\]\[surfaceKey\]/);
  assert.match(config, /aven_logo_horizontal_no_tagline_light_ui_4096\.svg/);
  assert.match(config, /aven_logo_horizontal_no_tagline_dark_ui_4096\.svg/);
  assert.match(config, /aven_logo_horizontal_light_ui_4096\.svg/);
  assert.match(config, /aven_logo_horizontal_dark_ui_4096\.svg/);
  assert.match(config, /aven_logo_vertical_light_ui_4096\.svg/);
  assert.match(config, /aven_logo_vertical_dark_ui_4096\.svg/);
  assert.match(config, /verticalNoTagline:[\s\S]*onLight: "\/brand\/aven\/aven_logo_vertical_no_tagline_dark_text_4096\.svg"/);
  assert.match(config, /verticalNoTagline:[\s\S]*onDark: "\/brand\/aven\/aven_logo_vertical_no_tagline_white_text_4096\.svg"/);
  assert.match(config, /mark:[\s\S]*aven-icon-gradient\.svg/);
});

test("Login renders the official vertical Full HD lockup in desktop and mobile auth layouts", () => {
  const auth = read("components/auth/auth-layout.tsx");
  const verticalOccurrences = auth.match(/variant="vertical"/g) ?? [];
  assert.equal(verticalOccurrences.length, 2);
  assert.doesNotMatch(auth, /variant="horizontal"/);
  assert.doesNotMatch(auth, />\s*AVEN\s*</i);
});

test("Sidebar keeps centralized branding with the requested expanded and collapsed Full HD mappings", () => {
  const shell = read("components/app-shell/application-shell.tsx");
  const component = read("components/brand/brand-logo.tsx");
  assert.match(shell, /<BrandLogo variant="wordmark" decorative \/>/);
  assert.match(shell, /<BrandLogo variant="verticalNoTagline" decorative \/>/);
  assert.match(component, /variant === "wordmark"\) return "horizontalNoTagline"/);
  assert.doesNotMatch(shell, /<BrandLogo variant="symbol" decorative \/>/);
  assert.doesNotMatch(shell, /\/brand\/aven\//);
});

test("primary branding does not use CSS transforms to manufacture light or dark variants", () => {
  const brandStyles = read("components/brand/brand-logo.module.css");
  const shellStyles = read("components/app-shell/app-shell.module.css");
  const authStyles = read("components/auth/auth-layout.module.css");
  const source = `${brandStyles}\n${shellStyles}\n${authStyles}`;
  assert.doesNotMatch(source, /filter:\s*(?:invert|brightness)\(/);
  assert.doesNotMatch(source, /mix-blend-mode:/);
});

test("root metadata keeps the official favicon and Apple touch assets", () => {
  const layout = read("app/layout.tsx");
  assert.match(layout, /brand\.assets\.icons\.favicon/);
  assert.match(layout, /brand\.assets\.icons\.appleTouch/);
});
