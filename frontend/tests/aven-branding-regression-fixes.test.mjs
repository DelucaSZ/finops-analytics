import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

test("collapsed sidebar uses the requested Full HD vertical no-tagline lockup", () => {
  const shell = read("components", "app-shell", "application-shell.tsx");
  const styles = read("components", "app-shell", "app-shell.module.css");
  const brand = read("lib", "brand.ts");

  assert.match(shell, /<BrandLogo variant="verticalNoTagline" decorative \/>/);
  assert.match(brand, /aven_logo_vertical_no_tagline_dark_text_4096\.svg/);
  assert.match(brand, /aven_logo_vertical_no_tagline_white_text_4096\.svg/);
  assert.match(styles, /\.brandMark[\s\S]*var\(--shell-brand-mark-size\)/);
  assert.match(styles, /html\[data-sidebar="collapsed"\][\s\S]*\.brandMark[\s\S]*display: block/);
  assert.doesNotMatch(shell, />\s*A\s*</);
});

test("login hero contains only the official Aven logo and no manual marketing copy", () => {
  const layout = read("components", "auth", "auth-layout.tsx");
  const styles = read("components", "auth", "auth-layout.module.css");
  const tokens = read("app", "styles", "tokens", "components.css");

  assert.match(layout, /variant="vertical"/);
  assert.match(layout, /className=\{styles\.brandHero\}/);
  assert.doesNotMatch(layout, /FINOPS MULTI-CLOUD|Complexidade por baixo|brandCopy|brandEyebrow|brandPrinciple/);
  assert.match(styles, /\.brandPanel[\s\S]*align-items: center[\s\S]*justify-content: center/);
  assert.match(styles, /\.brandLogo[\s\S]*--auth-brand-hero-inline-size/);
  assert.match(tokens, /--auth-brand-hero-inline-size: calc\(var\(--space-16\) \* 10\)/);
  assert.match(tokens, /--auth-brand-hero-medium-inline-size: calc\(var\(--space-16\) \* 7\)/);
});

test("narrow auth layouts preserve the vertical Full HD login branding", () => {
  const layout = read("components", "auth", "auth-layout.tsx");
  const styles = read("components", "auth", "auth-layout.module.css");

  assert.match(layout, /variant="vertical"[\s\S]*className=\{styles\.mobileLogo\}/);
  assert.doesNotMatch(layout, /variant="horizontal"[\s\S]*className=\{styles\.mobileLogo\}/);
  assert.match(styles, /@media \(max-width: 42rem\)[\s\S]*\.brandPanel[\s\S]*display: none/);
  assert.match(styles, /@media \(max-width: 42rem\)[\s\S]*\.mobileBrand[\s\S]*display: grid/);
});
