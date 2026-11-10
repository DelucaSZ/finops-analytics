"use client";

import {useTranslations} from "next-intl";

const labels: Record<string, string> = {
  connected: "Conectada",
  untested: "Não testada",
  error: "Erro",
  pending: "Pendente",
  running: "Em andamento",
  success: "Concluída",
  completed: "Concluída",
  completed_with_warnings: "Com alertas",
  failed: "Falhou",
  open: "Aberta",
  treated: "Tratada",
  rejected: "Rejeitada",
  active: "Ativa",
  missing: "Ausente",
  resolved_externally: "Resolvida externamente",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
};

const translationKeys = {"connected":"connected","untested":"untested","error":"error","pending":"pending","running":"running","success":"success","completed":"completed","completed_with_warnings":"completedWithWarnings","failed":"failed","open":"open","treated":"treated","rejected":"rejected","active":"active","missing":"missing","resolved_externally":"resolvedExternally","high":"high","medium":"medium","low":"low"} as const;

const humanStatuses = new Set(["open", "treated", "rejected"]);
const presenceStatuses = new Set(["active", "missing", "resolved_externally"]);

export function statusLabel(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  return labels[normalized] || value;
}

export function StatusBadge({ value, label }: { value: string; label?: string }) {
  const t = useTranslations("common.status");
  const normalized = String(value || "").trim().toLowerCase();
  const kind = presenceStatuses.has(normalized)
    ? "presence"
    : humanStatuses.has(normalized)
      ? "human"
      : "generic";
  return (
    <span
      className={`status-badge status-${normalized || "unknown"} ${kind}-status-badge`}
      data-status={normalized || "unknown"}
      data-status-kind={kind}
    >
      {label ?? (normalized in translationKeys ? t(translationKeys[normalized as keyof typeof translationKeys]) : value)}
    </span>
  );
}
