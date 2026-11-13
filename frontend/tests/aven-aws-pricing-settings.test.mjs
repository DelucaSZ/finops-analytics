import test from "node:test";
import assert from "node:assert/strict";
import { readFile, access } from "node:fs/promises";
import { settingsTabsForRole, isAdminOnlySettingsPath } from "../lib/settings-navigation.mjs";
import { formatAwsPrice } from "../lib/aws-pricing.mjs";
import ptBR from "../i18n/messages/pt-BR.json" with { type: "json" };
import enUS from "../i18n/messages/en-US.json" with { type: "json" };

test("AWS pricing is an admin-only Settings tab without removing OCI pricing", async () => {
  const admin = settingsTabsForRole("admin").map((tab) => tab.href);
  const viewer = settingsTabsForRole("viewer").map((tab) => tab.href);
  assert.ok(admin.includes("/settings/pricing/aws"));
  assert.ok(admin.includes("/settings/pricing/oci"));
  assert.ok(!viewer.includes("/settings/pricing/aws"));
  assert.equal(isAdminOnlySettingsPath("/settings/pricing/aws"), true);
  assert.equal(isAdminOnlySettingsPath("/settings/pricing/aws/details"), true);
  await access(new URL("../app/settings/pricing/aws/page.tsx", import.meta.url));
  await access(new URL("../app/settings/pricing/oci/page.tsx", import.meta.url));
});

test("rates preserve small USD decimals and never format missing as zero", () => {
  assert.match(formatAwsPrice("0.00425000", "en-US"), /0\.00425000/);
  assert.match(formatAwsPrice("0.00425000", "pt-BR"), /0,00425000/);
  assert.match(formatAwsPrice("0.00000000", "en-US"), /0\.00000000/);
  assert.equal(formatAwsPrice("", "pt-BR"), "—");
  assert.equal(formatAwsPrice("NaN"), "—");
  assert.equal(formatAwsPrice("0.123456789"), "—");
  assert.match(formatAwsPrice("9007199254740993.12345678", "en-US"), /9,007,199,254,740,993\\.12345678/);
});

test("AWS pricing translations and page behavior cover both locales", async () => {
  const keys = Object.keys(ptBR.settings.awsPricing).sort();
  assert.deepEqual(keys, Object.keys(enUS.settings.awsPricing).sort());
  assert.deepEqual(
    Object.keys(ptBR.settings.awsPricing.states).sort(),
    Object.keys(enUS.settings.awsPricing.states).sort(),
  );
  assert.deepEqual(
    Object.keys(ptBR.settings.awsPricing.errors).sort(),
    Object.keys(enUS.settings.awsPricing.errors).sort(),
  );
  const page = await readFile(
    new URL("../app/settings/pricing/aws/page.tsx", import.meta.url), "utf8",
  );
  assert.match(page, /AbortController/);
  assert.match(page, /\/pricing\/aws\/rates/);
  assert.match(page, /\/pricing\/aws\/sync\/coverage/);
  assert.match(page, /\/pricing\/aws\/sync\/requests/);
  assert.match(page, /window\.confirm/);
  assert.doesNotMatch(page, /pricing\.us-east-1\.amazonaws\.com/);
});
