import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";

const rootUrl = new URL("../", import.meta.url);
const appUrl = new URL("app/", rootUrl);
const brandUrl = new URL("public/brand/aven/", rootUrl);

test("Aven browser metadata uses the official Brand Kit raster icons", async () => {
  const layout = await readFile(new URL("layout.tsx", appUrl), "utf8");

  await Promise.all([
    access(new URL("favicon.ico", brandUrl)),
    access(new URL("apple-touch-icon.png", brandUrl)),
  ]);

  assert.match(layout, /PRODUCT_NAME/);
  assert.match(layout, /brand\.assets\.icons\.favicon/);
  assert.match(layout, /brand\.assets\.icons\.appleTouch/);
  assert.doesNotMatch(layout, /image\/svg\+xml/);
  assert.doesNotMatch(layout, /DeepOps|NuvemIQ/);
});

test("file-based SVG metadata no longer overrides the official Aven favicon configuration", async () => {
  await assert.rejects(access(new URL("icon.svg", appUrl)), { code: "ENOENT" });
});
