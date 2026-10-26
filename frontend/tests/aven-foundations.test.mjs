import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const rootUrl = new URL("../", import.meta.url);
const appUrl = new URL("app/", rootUrl);
const tokensUrl = new URL("app/styles/tokens/", rootUrl);

async function read(relativeUrl) {
  return readFile(new URL(relativeUrl, rootUrl), "utf8");
}

function declaration(css, token) {
  const match = css.match(new RegExp(`${token.replaceAll("-", "\\-")}\\s*:\\s*([^;]+);`));
  return match?.[1]?.trim() ?? null;
}

test("Aven typography uses the approved operational scale and named roles", async () => {
  const [primitives, foundations] = await Promise.all([
    readFile(new URL("primitives.css", tokensUrl), "utf8"),
    readFile(new URL("foundations.css", tokensUrl), "utf8"),
  ]);

  const expectedSizes = {
    "--font-size-xs": "0.75rem",
    "--font-size-sm": "0.8125rem",
    "--font-size-md": "0.875rem",
    "--font-size-lg": "1rem",
    "--font-size-xl": "1.125rem",
    "--font-size-2xl": "1.25rem",
    "--font-size-3xl": "1.5rem",
    "--font-size-4xl": "1.875rem",
    "--font-size-5xl": "2.25rem",
  };

  for (const [token, value] of Object.entries(expectedSizes)) {
    assert.equal(declaration(primitives, token), value, `${token} must use the approved scale`);
  }

  for (const weight of ["regular", "medium", "semibold", "bold"]) {
    assert.ok(primitives.includes(`--font-weight-${weight}:`));
  }

  for (const role of ["display-lg", "heading-xl", "heading-lg", "body-md", "body-sm", "label-md", "label-sm", "caption", "kpi-lg", "table-header", "table-body", "code"]) {
    assert.match(foundations, new RegExp(`--type-${role}-(family|size):`), `missing semantic typography role ${role}`);
  }

  assert.ok(foundations.includes("--font-variant-numeric-tabular: tabular-nums;"));
});

test("Inter and Sora are delivered through the framework-native font loader with only approved weights", async () => {
  const layout = await readFile(new URL("layout.tsx", appUrl), "utf8");

  assert.match(layout, /from "next\/font\/google"/);
  assert.match(layout, /Inter\(\{/);
  assert.match(layout, /Sora\(\{/);
  assert.match(layout, /weight: \["400", "500", "600", "700"\]/g);
  assert.match(layout, /variable: "--aven-font-inter"/);
  assert.match(layout, /variable: "--aven-font-sora"/);
  assert.match(layout, /className=\{`\$\{inter\.variable\} \$\{sora\.variable\}`\}/);
});

test("Light and Dark use distinct elevation strategies", async () => {
  const [light, dark] = await Promise.all([
    readFile(new URL("semantic-light.css", tokensUrl), "utf8"),
    readFile(new URL("semantic-dark.css", tokensUrl), "utf8"),
  ]);

  assert.notEqual(declaration(light, "--shadow-md"), declaration(dark, "--shadow-md"));
  assert.equal(declaration(light, "--elevation-1-shadow"), "var(--shadow-xs)");
  assert.equal(declaration(dark, "--elevation-1-shadow"), "var(--shadow-none)");
  assert.equal(declaration(dark, "--elevation-2-border"), "var(--border-default)");
});

test("iconography has one library and one token-backed geometry API", async () => {
  const [packageJson, iconography, primitives] = await Promise.all([
    read("package.json"),
    read("lib/iconography.ts"),
    readFile(new URL("primitives.css", tokensUrl), "utf8"),
  ]);
  const pkg = JSON.parse(packageJson);

  assert.equal(typeof pkg.dependencies?.["lucide-react"], "string");
  assert.match(iconography, /import type \{ LucideProps \} from "lucide-react"/);
  assert.match(iconography, /md: "var\(--icon-size-md\)"/);
  assert.match(iconography, /default: "var\(--icon-stroke-default\)"/);
  assert.match(iconography, /size: iconSizes\.md/);
  assert.match(iconography, /strokeWidth: iconStrokeWidths\.default/);

  for (const token of ["--icon-size-xs", "--icon-size-sm", "--icon-size-md", "--icon-size-lg", "--icon-size-xl", "--icon-size-2xl", "--icon-size-3xl", "--icon-stroke-default"]) {
    assert.ok(primitives.includes(`${token}:`), `missing icon token ${token}`);
  }
});

test("foundation includes accessible hit targets and reduced-motion spinner behavior", async () => {
  const [primitives, foundations] = await Promise.all([
    readFile(new URL("primitives.css", tokensUrl), "utf8"),
    readFile(new URL("foundations.css", tokensUrl), "utf8"),
  ]);

  assert.equal(declaration(primitives, "--hit-target-min"), "36px");
  assert.equal(declaration(primitives, "--hit-target-touch"), "44px");
  assert.match(foundations, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(foundations, /--motion-spinner-iteration-count: 1;/);
});

test("Task 24.5 hardcode contract and readiness are documented", async () => {
  const foundationsDoc = await read("../docs/brand/aven/AVEN_FOUNDATIONS.md");

  assert.match(foundationsDoc, /A partir da Task 24\.5, nenhum novo componente visual deverá utilizar cores, border radius, spacing ou typography hardcoded\./);
  assert.match(foundationsDoc, /Is Task 24\.5 ready to start\?\s*\*\*YES\*\*/);

  for (const item of ["Colors", "Spacing", "Radius", "Font family", "Font size", "Font weight", "Line height", "Shadows", "Icons", "Theme awareness"]) {
    assert.match(foundationsDoc, new RegExp(`${item}: \\*\\*YES\\*\\*`));
  }
});
