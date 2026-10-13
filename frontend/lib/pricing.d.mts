export type PricingLifecycleStatus = "active" | "inactive" | "future" | "expired";

export function normalizeDecimalInput(value: unknown): string | null;
export function pricingLifecycleStatus(
  item: { enabled: boolean; effective_from: string; effective_until: string | null },
  now?: Date | string,
): PricingLifecycleStatus;
export function pricingStatusLabel(status: string): string;
export function unitLabel(unit: string): string;
export function sourceLabel(source: string): string;
export function formatBrlDecimal(value: string | number): string;
export function toDatetimeLocal(value?: Date | string): string;
export function datetimeLocalToIso(value: string): string | null;
