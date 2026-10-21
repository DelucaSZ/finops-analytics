import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageSource = await readFile(
  new URL("../app/opportunities/page.tsx", import.meta.url),
  "utf8",
);
const detailSource = await readFile(
  new URL("../components/opportunity-detail.tsx", import.meta.url),
  "utf8",
);

const confirmation =
  "Esta oportunidade foi rejeitada anteriormente. Reabri-la removerá a decisão de rejeição e a devolverá ao backlog operacional. Deseja continuar?";

test("historical rejected rows use explicit reopen instead of direct unarchive", () => {
  assert.match(pageSource, /finding\.status === "rejected"/);
  assert.match(pageSource, /`\/opportunities\/\$\{finding\.id\}\/reopen`/);
  assert.match(pageSource, /Reabrir oportunidade/);
  assert.ok(pageSource.includes(confirmation));
  assert.match(pageSource, /`\/opportunities\/\$\{finding\.id\}\/unarchive`/);
});

test("archived rejected detail uses reopen and explains persistent suppression", () => {
  assert.match(detailSource, /detail\.status === "rejected"/);
  assert.match(detailSource, /`\/opportunities\/\$\{detail\.id\}\/reopen`/);
  assert.match(detailSource, /Reabrir oportunidade/);
  assert.ok(detailSource.includes(confirmation));
  assert.ok(
    detailSource.includes(
      "Esta oportunidade continua sendo observada tecnicamente, mas permanece suprimida pela decisão de rejeição.",
    ),
  );
});
