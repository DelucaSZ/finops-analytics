export type DashboardQueryState = {
  provider: string;
  accountId: string;
};
export function parseDashboardSearchParams(value: string | URLSearchParams): DashboardQueryState;
export function buildDashboardApiQuery(state: DashboardQueryState): string;
export function patchDashboardUrl(
  current: string | URLSearchParams,
  patch: Record<string, string | null | undefined>,
): URLSearchParams;
export function scopedDashboardHref(
  path: string,
  state: DashboardQueryState,
  extra?: Record<string, string | number | null | undefined>,
): string;
