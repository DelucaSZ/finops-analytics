import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const root = new URL("../", import.meta.url);
const load = (path) => readFile(new URL(path, root), "utf8");

test("Aven font loading is independent of Google Fonts during Docker build", async () => {
  const layout = await load("app/layout.tsx");
  const primitives = await load("app/styles/tokens/primitives.css");
  const packageJson = JSON.parse(await load("package.json"));
  const lock = JSON.parse(await load("package-lock.json"));

  assert.doesNotMatch(layout, /next\\/font\\/google/);
  assert.match(layout, /@fontsource-variable\\/inter\\/wght\\.css/);
  assert.match(layout, /@fontsource-variable\\/sora\\/wght\\.css/);
  assert.match(primitives, /--aven-font-inter: "Inter Variable"/);
  assert.match(primitives, /--aven-font-sora: "Sora Variable"/);

  for (const name of ["@fontsource-variable/inter", "@fontsource-variable/sora"]) {
    assert.equal(packageJson.dependencies[name], "5.3.0");
    assert.equal(lock.packages[""].dependencies[name], "5.3.0");
    assert.equal(lock.packages[`node_modules/${name}`].version, "5.3.0");
    assert.match(lock.packages[`node_modules/${name}`].integrity, /^sha512-/);
  }
});
