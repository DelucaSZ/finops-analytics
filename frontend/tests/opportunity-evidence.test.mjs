import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("opportunity detail renders backend-owned evidence and historical observations", async () => {
  const detail = await readFile(
    new URL("../components/opportunity-detail.tsx", import.meta.url),
    "utf8",
  );
  const evidence = await readFile(
    new URL("../components/finding-evidence.tsx", import.meta.url),
    "utf8",
  );
  const types = await readFile(new URL("../lib/types.ts", import.meta.url), "utf8");

  assert.match(detail, /latest_evidence/);
  assert.match(detail, /latest_observation/);
  assert.match(detail, /Ver evidência desta coleta/);
  assert.match(detail, /Voltar à evidência mais recente/);
  assert.match(detail, /Histórico de decisões/);

  assert.match(evidence, /Por que o DeepOps chegou nessa conclusão\?/);
  assert.match(evidence, /Detalhes adicionais não disponíveis para esta análise/);
  assert.match(evidence, /Critério aplicado nesta coleta/);
  assert.match(evidence, /Principais responsáveis pelo crescimento/);
  assert.match(evidence, /Ver evidência técnica/);
  assert.doesNotMatch(evidence, /findingExplanation/);
  assert.doesNotMatch(evidence, /JSON\.stringify/);

  assert.match(types, /type OpportunityEvidence/);
  assert.match(types, /type EvidenceMetric/);
  assert.match(types, /evidence: OpportunityEvidence/);
});

test("opportunity list type does not require the full evidence payload", async () => {
  const types = await readFile(new URL("../lib/types.ts", import.meta.url), "utf8");
  const findingBlock = types.match(/export type Finding = \{([\s\S]*?)\n\};/);
  assert.ok(findingBlock);
  assert.doesNotMatch(findingBlock[1], /evidence:/);
});
