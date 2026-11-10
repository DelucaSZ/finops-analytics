import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createTranslator } from "next-intl";

const pageUrl = new URL("../app/settings/pricing/oci/page.tsx", import.meta.url);
const ptCatalog = new URL("../i18n/messages/pt-BR.json", import.meta.url);
const enCatalog = new URL("../i18n/messages/en-US.json", import.meta.url);

test("OCI Pricing admin page localizes catalog, validation, history and audit labels", async () => {
  const [source, ptRaw, enRaw] = await Promise.all([readFile(pageUrl, "utf8"), readFile(ptCatalog, "utf8"), readFile(enCatalog, "utf8")]);
  const pt = createTranslator({locale:"pt-BR",messages:JSON.parse(ptRaw),namespace:"settings.ociPricing"});
  const en = createTranslator({locale:"en-US",messages:JSON.parse(enRaw),namespace:"settings.ociPricing"});
  for (const key of ["title","newPrice","searchPlaceholder","noFiltered","noResults","loading","createVersion","nonDestructive","deactivateConfirm","auditEyebrow","auditLoading","auditEmpty","actionChanged","actionFuture","actorSystem"]) {
    assert.ok(pt(key).trim().length > 0, "Missing pt-BR " + key);
    assert.ok(en(key).trim().length > 0, "Missing en-US " + key);
  }
  assert.equal(pt("title"), "Pricing OCI");
  assert.equal(en("title"), "OCI Pricing");
  assert.ok(source.includes('title={t("title")}'));
  assert.ok(source.includes('t("deactivateConfirm")'));
  assert.ok(source.includes('t("recordCount",'));
  assert.ok(source.includes('t("auditLoading")'));
  assert.ok(source.includes('t("actionChanged")'));
  assert.ok(source.includes("normalizeDecimalInput"));
  for (const endpoint of ["/pricing/oci?", "/pricing/oci/meta", "/deactivate", "/history", "/audit?page="]) {
    assert.ok(source.includes(endpoint), "Missing endpoint " + endpoint);
  }
  assert.ok(source.includes('value="future"'));
  assert.ok(source.includes("JSON.stringify({ reason })"));
  assert.ok(source.includes("reason: normalizedReason"));
  assert.ok(source.includes("onSaved(t(\"newVersionCreated\""));
  assert.ok(source.includes("auditDiff(event, locale, auditWords)"));
});

test("OCI Pricing editing still guards immutable identities and uses canonical payloads", async () => {
  const source = await readFile(pageUrl, "utf8");
  for (const field of ["service","sku","unit"]) assert.ok(source.includes(`value={${field}}`));
  assert.ok(source.match(/disabled=\{mode === "edit" \|\| saving\}/g)?.length >= 3);
  assert.ok(source.includes('<ReadOnlyField label={t("provider")} value="OCI" />'));
  assert.ok(source.includes('<ReadOnlyField label={t("currency")} value="BRL" />'));
  assert.ok(source.includes("price: normalizedPrice"));
  assert.ok(source.includes("effective_from: startsAt"));
  assert.ok(source.includes("onSaved(t(\"priceCreated\""));
  assert.ok(source.includes('locale === "en-US" ? "0.00000000" : "0,00000000"'));
});
