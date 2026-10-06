export const SCHEDULE_INTERVAL_OPTIONS = [
  { value: 12, label: "A cada 12 horas" },
  { value: 24, label: "Diariamente" },
  { value: 168, label: "Semanalmente" },
];

export function scheduleIntervalLabel(hours) {
  return SCHEDULE_INTERVAL_OPTIONS.find((option) => option.value === Number(hours))?.label
    || `A cada ${Number(hours)}h`;
}

export function scheduleSummary(account, capabilities) {
  if (!capabilities?.scheduling) return "Não implementado";
  if (!account.schedule_enabled) return "Desativado";
  return scheduleIntervalLabel(account.scan_interval_hours);
}
