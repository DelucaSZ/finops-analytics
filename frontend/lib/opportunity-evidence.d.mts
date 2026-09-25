import type {
  OpportunityEvidence,
  OpportunityObservation,
} from "./types";

export function isStructuredEvidence(
  value: unknown,
): value is OpportunityEvidence;

export function selectObservation(
  latestObservation: OpportunityObservation | null,
  observations: OpportunityObservation[],
  selectedObservationId: string | null,
): OpportunityObservation | null;

export function evidenceForSelection(
  fallbackEvidence: OpportunityEvidence | Record<string, unknown> | undefined,
  latestObservation: OpportunityObservation | null,
  observations: OpportunityObservation[],
  selectedObservationId: string | null,
): {
  observation: OpportunityObservation | null;
  evidence: OpportunityEvidence | Record<string, unknown>;
};
