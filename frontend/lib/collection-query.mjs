export const COLLECTION_STATUSES = {
  RUNNING: "Em andamento",
  SUCCESS: "Concluída",
  FAILED: "Falhou",
};
export const COLLECTION_SORTS = ["started_at", "opportunities_found"];
const filterKeys = [
  "provider",
  "account_id",
  "status",
  "date_from",
  "date_to",
  "analyzer_version",
];
const positive = (value, fallback) =>
  /^\d+$/.test(value || "") &&
  Number(value) > 0 &&
  Number.isSafeInteger(Number(value))
    ? Number(value)
    : fallback;

export function parseCollectionQuery(value) {
  const params = new URLSearchParams(value || "");
  const result = Object.fromEntries(
    filterKeys.map((key) => [key, params.get(key) || ""]),
  );
  if (!(result.status in COLLECTION_STATUSES)) result.status = "";
  return {
    ...result,
    page: positive(params.get("page"), 1),
    page_size: [25, 50, 100].includes(Number(params.get("page_size")))
      ? Number(params.get("page_size"))
      : 50,
    sort: COLLECTION_SORTS.includes(params.get("sort"))
      ? params.get("sort")
      : "started_at",
    order: params.get("order") === "asc" ? "asc" : "desc",
  };
}

export function buildCollectionQuery(state) {
  const params = new URLSearchParams();
  for (const key of [...filterKeys, "page", "page_size", "sort", "order"]) {
    if (state[key] !== "" && state[key] != null)
      params.set(key, String(state[key]));
  }
  return params.toString();
}

export function patchCollectionQuery(current, patch) {
  const state = { ...parseCollectionQuery(current), ...patch };
  if (!("page" in patch)) state.page = 1;
  return buildCollectionQuery(state);
}

export function collectionOpportunitiesUrl(id) {
  return `/opportunities?${new URLSearchParams({ collection_run_id: id, status: "open", page: "1" })}`;
}

export function localDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function durationLabel(run, now = Date.now()) {
  const elapsed =
    run.duration_seconds ??
    (run.status === "RUNNING"
      ? (now - new Date(run.started_at).getTime()) / 1000
      : null);
  if (elapsed == null || !Number.isFinite(elapsed)) return "—";
  const seconds = Math.max(0, Math.floor(elapsed));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const text = `${hours ? `${hours}h ` : ""}${minutes ? `${minutes}m ` : ""}${seconds % 60}s`;
  return run.status === "RUNNING" ? `Em andamento há ${text}` : text;
}
