import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BRAND_DIR = path.join(ROOT, "public", "brand", "aven");
const read = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), "utf8");

const fullHdLogoAssets = [
  "aven_logo_horizontal_dark_ui_4096.png",
  "aven_logo_horizontal_light_ui_4096.png",
  "aven_logo_horizontal_no_tagline_dark_ui_4096.png",
  "aven_logo_horizontal_no_tagline_light_ui_4096.png",
  "aven_logo_vertical_dark_ui_4096.png",
  "aven_logo_vertical_light_ui_4096.png",
];

const legacyRasterLogos = [
  "aven-logo-horizontal-on-dark.png",
  "aven-logo-horizontal-on-light.png",
  "aven-logo-vertical-on-dark.png",
  "aven-logo-vertical-on-light.png",
];

function pngDimensions(file) {
  const buffer = fs.readFileSync(file);
  assert.equal(buffer.toString("ascii", 1, 4), "PNG", `${path.basename(file)} should be a PNG`);
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

test("Aven Full HD production lockups are versioned under the frontend brand directory", () => {
  for (const asset of fullHdLogoAssets) {
    const file = path.join(BRAND_DIR, asset);
    assert.ok(fs.existsSync(file), `${asset} should exist`);
    assert.ok(fs.statSync(file).size > 0, `${asset} should not be empty`);
    const dimensions = pngDimensions(file);
    assert.equal(dimensions.width, 4096, `${asset} should keep the 4096px master width`);
    assert.equal(dimensions.height, asset.includes("vertical") ? 4096 : 1600);
  }

  for (const asset of legacyRasterLogos) {
    assert.equal(fs.existsSync(path.join(BRAND_DIR, asset)), false, `${asset} should be removed`);
  }
});

test("AvenLogo centralizes Full HD lockup selection and theme-aware surfaces", () => {
  const component = read("components/brand/brand-logo.tsx");
  const config = read("lib/brand.ts");

  assert.match(component, /export type AvenLogoVariant = "horizontal" \| "horizontalNoTagline" \| "vertical" \| "mark"/);
  assert.match(component, /surfaceKey = surface === "dark" \? "onDark" : "onLight"/);
  assert.match(component, /if \(variant === "wordmark"\) return "horizontalNoTagline"/);
  assert.match(component, /if \(variant === "symbol"\) return "horizontal"/);
  assert.match(component, /brand\.assets\.logo\[variant\]\[surfaceKey\]/);
  assert.match(config, /aven_logo_horizontal_no_tagline_light_ui_4096\.png/);
  assert.match(config, /aven_logo_horizontal_no_tagline_dark_ui_4096\.png/);
  assert.match(config, /aven_logo_horizontal_light_ui_4096\.png/);
  assert.match(config, /aven_logo_horizontal_dark_ui_4096\.png/);
  assert.match(config, /aven_logo_vertical_light_ui_4096\.png/);
  assert.match(config, /aven_logo_vertical_dark_ui_4096\.png/);
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
  assert.match(shell, /<BrandLogo variant="symbol" decorative \/>/);
  assert.match(component, /variant === "wordmark"\) return "horizontalNoTagline"/);
  assert.match(component, /variant === "symbol"\) return "horizontal"/);
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

test("root metadata keeps the refreshed official favicon and Apple touch assets", () => {
  const layout = read("app/layout.tsx");
  assert.match(layout, /brand\.assets\.icons\.favicon/);
  assert.match(layout, /brand\.assets\.icons\.appleTouch/);
});
