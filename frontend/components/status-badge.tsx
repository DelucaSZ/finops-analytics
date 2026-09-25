const labels: Record<string, string> = {
  connected: "Conectada",
  untested: "Não testada",
  error: "Erro",
  pending: "Pendente",
  running: "Executando",
  completed: "Concluída",
  completed_with_warnings: "Com alertas",
  failed: "Falhou",
  open: "Aberta",
  treated: "Tratada",
  rejected: "Rejeitada",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
};

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge status-${value}`}>{labels[value] || value}</span>;
}
