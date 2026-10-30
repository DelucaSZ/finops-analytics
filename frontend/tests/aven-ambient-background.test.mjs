import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...segments) => fs.readFileSync(path.join(ROOT, ...segments), "utf8");

const ambientComponent = () => read("components", "aven", "ambient-background.tsx");
const ambientStyles = () => read("components", "aven", "ambient-background.module.css");
const darkSvg = () => read("public", "brand", "aven", "aven-ambient-background-dark.svg");
const lightSvg = () => read("public", "brand", "aven", "aven-ambient-background-light.svg");

test("Aven ambient assets are independent vector SVG sources for light and dark", () => {
  for (const [name, source] of [["dark", darkSvg()], ["light", lightSvg()]]) {
    assert.match(source, /<svg\b/);
    assert.match(source, /viewBox="0 0 1920 1080"/);
    assert.match(source, /preserveAspectRatio="xMidYMid slice"/);
    assert.match(source, /vector-effect="non-scaling-stroke"/);
    assert.doesNotMatch(source, /<image\b|data:image|base64|<script\b|<animate\b|<filter\b/i, `${name} ambient asset must stay native vector-only`);
  }
  assert.notEqual(darkSvg(), lightSvg(), "light and dark must use independent source assets");
});

test("ambient asset paths are centralized in the Aven brand contract", () => {
  const brand = read("lib", "brand.ts");
  const component = ambientComponent();

  assert.match(brand, /ambient: Object\.freeze\(\{/);
  assert.match(brand, /light: "\/brand\/aven\/aven-ambient-background-light\.svg"/);
  assert.match(brand, /dark: "\/brand\/aven\/aven-ambient-background-dark\.svg"/);
  assert.match(component, /brand\.assets\.ambient\.light/);
  assert.match(component, /brand\.assets\.ambient\.dark/);
});

test("ambient primitive follows the existing resolved Theme Engine without parallel listeners", () => {
  const component = ambientComponent();
  const styles = ambientStyles();

  assert.match(styles, /html\[data-theme="dark"\][\s\S]*\.lightAsset[\s\S]*display: none/);
  assert.match(styles, /html\[data-theme="dark"\][\s\S]*\.darkAsset[\s\S]*display: block/);
  assert.doesNotMatch(component, /useTheme|matchMedia|localStorage|useEffect/);
});

test("ambient background is integrated globally above the fallback canvas and below all application content", () => {
  const layout = read("app", "layout.tsx");
  const styles = ambientStyles();

  assert.match(layout, /import \{ AvenAmbientBackground \} from "@\/components\/aven\/ambient-background"/);
  assert.match(layout, /<ThemeProvider>[\s\S]*<AvenAmbientBackground>[\s\S]*<ToastProvider>[\s\S]*<AppShell>\{children\}<\/AppShell>/);
  assert.match(styles, /\.viewport[\s\S]*background: var\(--application-background\)/);
  assert.match(styles, /\.background[\s\S]*position: fixed/);
  assert.match(styles, /\.background[\s\S]*inset: var\(--space-0\)/);
  assert.match(styles, /\.background[\s\S]*pointer-events: none/);
  assert.match(styles, /\.background[\s\S]*overflow: hidden/);
  assert.match(styles, /\.asset[\s\S]*object-fit: cover/);
  assert.match(styles, /\.content[\s\S]*position: relative/);
  assert.match(styles, /\.content[\s\S]*z-index: var\(--z-index-sticky\)/);
});

test("shell and authentication surfaces expose the global ambient canvas instead of repainting it", () => {
  const componentTokens = read("app", "styles", "tokens", "components.css");
  const authStyles = read("components", "auth", "auth-layout.module.css");

  assert.match(componentTokens, /--shell-background: var\(--page-background\);/);
  assert.match(authStyles, /\.page[\s\S]*background: var\(--page-background\)/);
  assert.doesNotMatch(authStyles, /background:\s*var\(--application-background\)/);
});

test("ambient primitive is decorative and cannot capture interaction", () => {
  const component = ambientComponent();
  const styles = ambientStyles();

  assert.match(component, /aria-hidden="true"/);
  assert.match(component, /alt=""/);
  assert.match(component, /draggable=\{false\}/);
  assert.match(styles, /pointer-events: none/);
});
