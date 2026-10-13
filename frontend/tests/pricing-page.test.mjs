import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const pageUrl = new URL("../app/settings/pricing/oci/page.tsx", import.meta.url);

test("OCI pricing admin page exposes the required catalog workflows", async () => {
  const source = await readFile(pageUrl, "utf8");

  assert.ok(source.includes('title="Pricing OCI"'));
  assert.ok(source.includes("Novo preço"));
  assert.ok(source.includes("BRL"));
  assert.ok(source.includes("/pricing/oci?"));
  assert.ok(source.includes("/pricing/oci/meta"));
  assert.ok(source.includes("status=future") || source.includes('value="future"'));
  assert.ok(source.includes("Nenhum preço encontrado."));
  assert.ok(source.includes("Nenhum preço corresponde aos filtros selecionados."));
  assert.ok(source.includes("Carregando preços…"));
  assert.ok(source.includes("normalizeDecimalInput"));
  assert.ok(source.includes("Criar nova vigência"));
  assert.ok(source.includes("Alteração não destrutiva"));
  assert.ok(source.includes("/deactivate"));
  assert.ok(source.includes("Desativar este preço?"));
  assert.ok(source.includes("/history"));
});

test("identity fields are protected while editing an existing pricing version", async () => {
  const source = await readFile(pageUrl, "utf8");

  const protectedFields = ["service", "sku", "unit"];
  for (const field of protectedFields) {
    assert.ok(source.includes(`value={${field}}`));
  }
  assert.ok(source.match(/disabled=\{mode === "edit" \|\| saving\}/g)?.length >= 3);
  assert.ok(source.includes('<ReadOnlyField label="Provider" value="OCI" />'));
  assert.ok(source.includes('<ReadOnlyField label="Moeda" value="BRL" />'));
});
