export type HistorySnapshotQueryOptions = {
  cycleId?: string;
  page?: number;
  pageSize?: number;
  sort?: string;
  order?: string;
  provider?: string;
  status?: string;
  severity?: string;
  search?: string;
};

export type HistoryCycleLike = {
  id: string;
  status: string;
};

export type HistoryMoneyRow = {
  currency: string;
  amount: string | number;
};

export function buildHistorySnapshotQuery(
  options?: HistorySnapshotQueryOptions,
): string;

export function chooseHistoryCycle<T extends HistoryCycleLike>(
  cycles: T[],
  requestedId?: string,
): T | null;

export function cycleStateLabel(status: string): string;

export function historyMoneyRows(
  totals: Record<string, unknown> | null | undefined,
  key: string,
): HistoryMoneyRow[];
