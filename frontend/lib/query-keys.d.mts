export type QueryKey = readonly unknown[];

export const cachePolicy: {
  operational: { staleTime: number; gcTime: number };
  detail: { staleTime: number; gcTime: number };
  metadata: { staleTime: number; gcTime: number };
  comparison: { staleTime: number; gcTime: number };
};

export const queryKeys: {
  dashboard: {
    all: QueryKey;
    summary(provider?: string | null, accountId?: string | null): QueryKey;
    health(provider?: string | null, accountId?: string | null): QueryKey;
  };
  opportunities: {
    all: QueryKey;
    list(query: string): QueryKey;
    stats(query: string): QueryKey;
    options(provider?: string | null, accountId?: string | null): QueryKey;
    detail(id: string): QueryKey;
    history(id: string, page: number, pageSize: number): QueryKey;
    statusHistory(id: string): QueryKey;
  };
  collections: {
    all: QueryKey;
    list(query: string): QueryKey;
    detail(id: string): QueryKey;
    options(provider?: string | null, search?: string | null, limit?: number): QueryKey;
    picker(): QueryKey;
    comparison(
      targetId: string,
      baselineId: string | null | undefined,
      category: string,
      page: number,
      pageSize: number,
    ): QueryKey;
    comparisonOptions(targetId: string): QueryKey;
  };
};
