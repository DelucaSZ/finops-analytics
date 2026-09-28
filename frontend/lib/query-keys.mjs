const normalize = (value) => {
  if (value === undefined || value === null) return null;
  const text = String(value).trim();
  return text || null;
};

export const cachePolicy = {
  operational: { staleTime: 45_000, gcTime: 5 * 60_000 },
  detail: { staleTime: 2 * 60_000, gcTime: 10 * 60_000 },
  metadata: { staleTime: 5 * 60_000, gcTime: 30 * 60_000 },
  comparison: { staleTime: 2 * 60_000, gcTime: 15 * 60_000 },
};

export const queryKeys = {
  dashboard: {
    all: ["dashboard"],
    summary: (provider, accountId) => [
      "dashboard",
      "summary",
      { provider: normalize(provider), account_id: normalize(accountId) },
    ],
    health: (provider, accountId) => [
      "dashboard",
      "health",
      { provider: normalize(provider), account_id: normalize(accountId) },
    ],
  },
  opportunities: {
    all: ["opportunities"],
    list: (query) => ["opportunities", "list", String(query || "")],
    stats: (query) => ["opportunities", "stats", String(query || "")],
    options: (provider, accountId) => [
      "opportunities",
      "options",
      { provider: normalize(provider), account_id: normalize(accountId) },
    ],
    detail: (id) => ["opportunities", "detail", String(id || "")],
    history: (id, page, pageSize) => [
      "opportunities",
      "history",
      String(id || ""),
      { page: Number(page), page_size: Number(pageSize) },
    ],
    statusHistory: (id) => [
      "opportunities",
      "status-history",
      String(id || ""),
    ],
  },
  collections: {
    all: ["collections"],
    list: (query) => ["collections", "list", String(query || "")],
    detail: (id) => ["collections", "detail", String(id || "")],
    options: (provider, search, limit = 50) => [
      "collections",
      "options",
      {
        provider: normalize(provider),
        search: normalize(search),
        limit: Number(limit),
      },
    ],
    picker: () => ["collections", "picker", { limit: 100 }],
    comparison: (targetId, baselineId, category, page, pageSize) => [
      "collections",
      "comparison",
      {
        target_id: String(targetId || ""),
        baseline_id: normalize(baselineId),
        category: String(category || ""),
        page: Number(page),
        page_size: Number(pageSize),
      },
    ],
    comparisonOptions: (targetId) => [
      "collections",
      "comparison-options",
      String(targetId || ""),
    ],
  },
};
