import assert from "node:assert/strict";
import test from "node:test";

import {
  evidenceForSelection,
  isStructuredEvidence,
  selectObservation,
} from "../lib/opportunity-evidence.mjs";

const structured = {
  schema_version: 1,
  summary: "A instância está parada.",
  metrics: [{ key: "days", label: "Tempo parada", value: 17, unit: "days" }],
  details: { state: "stopped" },
  rule: {
    key: "ec2_stopped_with_ebs",
    name: "EC2 desligada mantendo EBS",
    description: "Descrição",
    criteria: [],
  },
  decision_parameters: {},
  source: {
    provider: "aws",
    system: "AWS EC2",
    evaluated_at: "2026-09-25T12:00:00+00:00",
  },
  limitations: [],
};

test("recognizes the versioned evidence contract", () => {
  assert.equal(isStructuredEvidence(structured), true);
  assert.equal(isStructuredEvidence({ state: "stopped" }), false);
  assert.equal(isStructuredEvidence(null), false);
});

test("uses the latest observation by default", () => {
  const latest = { id: "obs-2", evidence: structured };
  const older = { id: "obs-1", evidence: { schema_version: 1, summary: "Older" } };
  assert.equal(selectObservation(latest, [latest, older], null), latest);
});

test("selects historical evidence without recalculating it", () => {
  const latest = { id: "obs-2", evidence: structured };
  const historicalEvidence = {
    ...structured,
    summary: "A instância estava parada há 16 dias.",
    metrics: [{ key: "days", label: "Tempo parada", value: 16, unit: "days" }],
  };
  const older = { id: "obs-1", evidence: historicalEvidence };
  const selected = evidenceForSelection(
    {},
    latest,
    [latest, older],
    "obs-1",
  );
  assert.equal(selected.observation, older);
  assert.equal(selected.evidence, historicalEvidence);
  assert.equal(selected.evidence.metrics[0].value, 16);
});

test("falls back safely when no observation evidence exists", () => {
  const fallback = { description: "legacy" };
  const selected = evidenceForSelection(fallback, null, [], null);
  assert.equal(selected.observation, null);
  assert.equal(selected.evidence, fallback);
});
