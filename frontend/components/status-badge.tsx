const labels: Record<string, string> = {
  connected: "Conectada",
  untested: "Não testada",
  error: "Erro",
  pending: "Pendente",
  running: "Em andamento",
  success: "Concluída",
  completed: "Concluída",
  completed_with_warnings: "Concluída com avisos",
  failed: "Falhou",
  open: "Aberta",
  treated: "Tratada",
  rejected: "Rejeitada",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
};

export function statusLabel(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  return labels[normalized] || value || "—";
}

export function StatusBadge({ value }: { value: string }) {
  const normalized = String(value || "").trim().toLowerCase();
  return (
    <span className={`status-badge status-${normalized || "unknown"}`}>
      {statusLabel(value)}
    </span>
  );
}
