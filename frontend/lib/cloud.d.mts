export const PROVIDER_LABELS: Readonly<Record<string, string>>;
export function providerLabel(provider: string | null | undefined): string;
export function formatMoney(
  value: number | string,
  currency?: string,
  locale?: string,
): string;
