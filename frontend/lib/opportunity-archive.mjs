const FILTER_FIELDS = [
  ["provider", "provider"],
  ["accountId", "account_id"],
  ["region", "region"],
  ["service", "service"],
  ["resourceType", "resource_type"],
  ["status", "status"],
  ["presenceStatus", "presence_status"],
  ["severity", "severity"],
  ["rule", "rule"],
  ["collectionRunId", "collection_run_id"],
  ["resourceId", "resource_id"],
  ["search", "search"],
];

export function buildArchiveFilters(state) {
  const filters = {};
  for (const [stateKey, apiKey] of FILTER_FIELDS) {
    const value = state?.[stateKey];
    if (typeof value === "string" && value.trim()) filters[apiKey] = value.trim();
  }
  if (state?.current) filters.current = true;
  return filters;
}

export function buildArchiveScope(state, { archiveAll = false } = {}) {
  return {
    filters: archiveAll ? {} : buildArchiveFilters(state),
    archive_all: Boolean(archiveAll),
  };
}

export function archiveResultMessage(result) {
  const archived = Number(result?.archived || 0);
  const already = Number(result?.already_archived || 0);
  if (already > 0) {
    return `${archived.toLocaleString("pt-BR")} oportunidades arquivadas. ${already.toLocaleString("pt-BR")} já estavam no Histórico.`;
  }
  return `${archived.toLocaleString("pt-BR")} oportunidades foram arquivadas.`;
}

export function periodCloseResultMessage(result, label) {
  const snapshots = Number(result?.snapshots_created || 0).toLocaleString("pt-BR");
  const archived = Number(result?.archived || 0).toLocaleString("pt-BR");
  return `Período ${label} fechado com ${snapshots} snapshots e ${archived} oportunidades arquivadas.`;
}
