export function parseDashboardSearchParams(value) {
  const params = value instanceof URLSearchParams ? value : new URLSearchParams(value || "");
  return {
    provider: (params.get("provider") || "").trim().toLowerCase(),
    accountId: (params.get("account_id") || "").trim(),
  };
}

export function buildDashboardApiQuery(state) {
  const params = new URLSearchParams();
  if (state.provider) params.set("provider", state.provider);
  if (state.accountId) params.set("account_id", state.accountId);
  return params.toString();
}

export function patchDashboardUrl(current, patch) {
  const params = current instanceof URLSearchParams
    ? new URLSearchParams(current.toString())
    : new URLSearchParams(current || "");
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined || value === null || value === "") params.delete(key);
    else params.set(key, String(value));
  }
  return params;
}

export function scopedDashboardHref(path, state, extra = {}) {
  const params = new URLSearchParams();
  if (state.provider) params.set("provider", state.provider);
  if (state.accountId) params.set("account_id", state.accountId);
  for (const [key, value] of Object.entries(extra)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return `${path}${params.size ? `?${params.toString()}` : ""}`;
}
