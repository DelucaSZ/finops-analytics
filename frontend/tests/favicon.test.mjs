import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const appUrl = new URL("../app/", import.meta.url);

test("DeepOps favicon assets follow the Next.js App Router metadata convention", async () => {
  const [icon, layout] = await Promise.all([
    readFile(new URL("icon.svg", appUrl), "utf8"),
    readFile(new URL("layout.tsx", appUrl), "utf8"),
  ]);

  assert.match(icon, /#55e5b6/i);
  assert.match(icon, /#80f0cf/i);
  assert.match(icon, /stroke="#07120f"/i);
  assert.match(icon, /M4\.2 15\.1a7 7 0 1 1/);

  assert.doesNotMatch(layout, /rel=["']icon["']/i);
  assert.doesNotMatch(layout, /\bicons\s*:/);
});

test("favicon.ico contains legacy 16, 32 and 48 pixel entries", async () => {
  const favicon = await readFile(new URL("favicon.ico", appUrl));

  assert.equal(favicon.readUInt16LE(0), 0, "ICO reserved field must be zero");
  assert.equal(favicon.readUInt16LE(2), 1, "file must be an ICO image");

  const count = favicon.readUInt16LE(4);
  assert.equal(count, 3);

  const sizes = Array.from({ length: count }, (_, index) => {
    const offset = 6 + index * 16;
    const width = favicon[offset] || 256;
    const height = favicon[offset + 1] || 256;
    return [width, height];
  });

  assert.deepEqual(sizes, [
    [16, 16],
    [32, 32],
    [48, 48],
  ]);
});
