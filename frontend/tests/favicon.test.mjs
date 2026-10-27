import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";

const appUrl = new URL("../app/", import.meta.url);

test("Aven browser icon uses the official versioned gradient symbol", async () => {
  const [icon, layout] = await Promise.all([
    readFile(new URL("icon.svg", appUrl), "utf8"),
    readFile(new URL("layout.tsx", appUrl), "utf8"),
  ]);

  assert.match(icon, /#38B2F6/i);
  assert.match(icon, /#6366F1/i);
  assert.match(icon, /#8B5CF6/i);
  assert.match(icon, /M 42,398 L 51,407/);
  assert.doesNotMatch(icon, /#55e5b6|#80f0cf|#07120f/i);
  assert.match(layout, /PRODUCT_NAME/);
  assert.match(layout, /image\/svg\+xml/);
  assert.doesNotMatch(layout, /DeepOps|NuvemIQ/);
});

test("legacy DeepOps favicon.ico is not exposed while official Aven raster favicon is pending", async () => {
  await assert.rejects(access(new URL("favicon.ico", appUrl)), { code: "ENOENT" });
});
