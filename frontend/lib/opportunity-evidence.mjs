export function isStructuredEvidence(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      value.schema_version === 1 &&
      typeof value.summary === "string" &&
      Array.isArray(value.metrics) &&
      value.rule &&
      typeof value.rule === "object",
  );
}

export function selectObservation(latestObservation, observations, selectedObservationId) {
  if (selectedObservationId) {
    const selected = observations.find((item) => item.id === selectedObservationId);
    if (selected) return selected;
  }
  return latestObservation || observations[0] || null;
}

export function evidenceForSelection(
  fallbackEvidence,
  latestObservation,
  observations,
  selectedObservationId,
) {
  const observation = selectObservation(
    latestObservation,
    observations,
    selectedObservationId,
  );
  return {
    observation,
    evidence: observation?.evidence || fallbackEvidence || {},
  };
}
