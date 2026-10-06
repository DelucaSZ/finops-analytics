import type { CloudAccount, ProviderCapabilities } from "./types";

export type ScheduleIntervalOption = {
  value: number;
  label: string;
};

export const SCHEDULE_INTERVAL_OPTIONS: ScheduleIntervalOption[];
export function scheduleIntervalLabel(hours: number): string;
export function scheduleSummary(
  account: CloudAccount,
  capabilities?: ProviderCapabilities,
): string;
