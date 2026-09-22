import type { Finding } from "./types";
import { usd } from "./api";

export type EvidenceFact = { label: string; value: string };
export type CostContributor = { usageType: string; baseline: number; current: number; delta: number };

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function display(value: unknown): string {
  if (value === null || value === undefined) return "Não registrado";
  if (Array.isArray(value)) return value.map(display).join(", ") || "Nenhum";
  if (typeof value === "object") return Object.entries(record(value)).map(([key, item]) => `${key}: ${display(item)}`).join("; ") || "Nenhum";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "number") return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  return String(value);
}
function period(start: unknown, end: unknown): string {
  if (typeof start !== "string" || typeof end !== "string") return "Datas não registradas nesta varredura";
  const first = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  if (Number.isNaN(first.getTime()) || Number.isNaN(last.getTime())) return "Datas não registradas";
  last.setUTCDate(last.getUTCDate() - 1);
  const format = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" });
  return `${format.format(first)} a ${format.format(last)} (UTC)`;
}

// Explanations use only the evidence from this finding, never today's policy defaults.
export function findingExplanation(finding: Finding) {
  const e = finding.evidence || {};
  const policy = record(e.policy_config);
  const facts: EvidenceFact[] = [];
  const criteria: EvidenceFact[] = [];
  const notes: string[] = [];
  let summary = finding.description || "Consulte as evidências registradas para este recurso.";
  let source = "Inventário AWS";
  let contributors: CostContributor[] = [];
  const fact = (label: string, value: unknown) => { if (value !== undefined && value !== null) facts.push({ label, value: display(value) }); };
  const criterion = (label: string, value: unknown) => { if (value !== undefined && value !== null) criteria.push({ label, value: display(value) }); };

  switch (finding.rule_key) {
    case "cost_growth_anomaly": {
      source = "AWS Cost Explorer · UnblendedCost (USD)";
      const baseline = number(e.baseline_equivalent_usd);
      const current = number(e.current_spend_usd);
      const delta = number(e.delta_usd);
      const growth = baseline !== null && baseline > 0 ? number(e.growth_percent) : null;
      if (baseline !== null && current !== null && delta !== null) {
        summary = `${finding.service} em ${finding.region}: ${usd(current)} em ${display(e.comparison_period_days)} dias, contra ${usd(baseline)} esperados. Aumento de ${usd(delta)}${growth !== null ? ` (${display(growth)}%)` : "; sem percentual aplicável à base histórica"}.`;
        facts.push({ label: "Custo esperado no período recente", value: usd(baseline) }, { label: "Custo observado no período recente", value: usd(current) }, { label: "Aumento de custo", value: usd(delta) });
      }
      fact("Período de referência", period(e.baseline_start, e.baseline_end_exclusive));
      fact("Período recente", period(e.comparison_start, e.comparison_end_exclusive));
      if (number(e.baseline_total_usd) !== null) fact("Custo total da referência", usd(e.baseline_total_usd as number));
      fact("Dias de referência", e.baseline_period_days);
      fact("Dias comparados", e.comparison_period_days);
      criterion("Crescimento mínimo (%)", e.minimum_growth_percent ?? policy.minimum_growth_percent);
      criterion("Aumento mínimo (USD)", e.minimum_delta_usd ?? policy.minimum_delta_usd);
      criterion("Custo recente mínimo (USD)", e.minimum_current_spend_usd ?? policy.minimum_current_spend_usd);
      notes.push("Custo esperado = total da referência ÷ dias de referência × dias comparados. Aumento = custo recente − custo esperado. Percentual = aumento ÷ custo esperado × 100, apenas para base positiva.");
      notes.push("O alerta mede custo. Os tipos de uso indicam quais cobranças cresceram; não comprovam, isoladamente, aumento de consumo nem identificam a alteração ou o recurso que causou a alta.");
      if (baseline !== null && baseline <= 0) notes.push("Base zero ou negativa: o percentual não se aplica. O alerta considera os limites de custo recente e aumento em dólares.");
      if (e.estimated === true || e.breakdown_estimated === true) notes.push("A AWS marcou dados destes períodos como estimados; os valores podem ser revisados.");
      if (e.breakdown_status === "unavailable") notes.push("Não foi possível consultar os tipos de uso nesta varredura. A comparação por serviço/região continua disponível.");
      else if (e.breakdown_status !== "available") notes.push("Execute uma nova varredura para registrar as datas, os critérios e os tipos de uso que cresceram.");
      if (Array.isArray(e.cost_contributors)) contributors = e.cost_contributors.flatMap((value) => {
        const item = record(value);
        const previous = number(item.baseline_equivalent_usd), actual = number(item.current_spend_usd), change = number(item.delta_usd);
        return typeof item.usage_type === "string" && previous !== null && actual !== null && change !== null
          ? [{ usageType: item.usage_type, baseline: previous, current: actual, delta: change }] : [];
      });
      if (e.breakdown_status === "available" && !contributors.length) notes.push("Nenhum tipo de uso com aumento positivo foi retornado no detalhamento desta consulta.");
      notes.push("Economia ainda não estimada: o aumento detectado não equivale automaticamente a desperdício.");
      break;
    }
    case "ebs_unattached":
      fact("Estado do volume", e.state === "available" ? "Disponível, sem anexação" : e.state);
      fact("Capacidade (GiB)", e.size_gib); fact("Tipo do volume", e.volume_type); fact("Idade desde a criação (dias)", e.age_days);
      criterion("Idade mínima desde a criação (dias)", policy.minimum_age_days);
      notes.push("A idade é contada desde a criação do volume; não representa há quanto tempo ele está desanexado.");
      break;
    case "eip_unassociated":
      fact("IPv4 público", e.public_ip); fact("Alocação", e.allocation_id);
      criteria.push({ label: "Condição detectada", value: "Ausência de associação a instância e interface de rede" });
      break;
    case "snapshot_retention":
      fact("Idade (dias)", e.age_days); fact("Volume de origem", e.volume_id); fact("Tamanho do volume de origem (GiB)", e.volume_size_gib);
      criterion("Retenção (dias)", e.retention_days ?? policy.retention_days);
      criterion("Snapshots recentes preservados por volume", policy.preserve_last_per_volume);
      criterion("Preservar snapshots de AMIs", policy.preserve_ami_snapshots);
      notes.push("A economia é um limite superior calculado pelo tamanho do volume de origem. Snapshots são incrementais.");
      break;
    case "ec2_stopped_with_ebs":
      fact("Tipo da instância", e.instance_type); fact("Dias desligada", e.stopped_days);
      fact("Volumes cobrados", e.volumes); criterion("Tempo mínimo desligada (dias)", policy.minimum_stopped_days);
      if (e.stopped_days == null) notes.push("O horário de desligamento não foi identificado. A duração não está confirmada.");
      break;
    case "ec2_nonprod_outside_hours":
      fact("Tipo da instância", e.instance_type); fact("Tags observadas", e.tags);
      criterion("Fuso horário", e.timezone ?? policy.timezone);
      criterion("Início do expediente", e.business_hours_start ?? policy.business_hours_start);
      criterion("Fim do expediente", e.business_hours_end ?? policy.business_hours_end);
      criterion("Dias úteis (1 = segunda; 7 = domingo)", policy.business_days);
      criterion("Tags de ambiente", policy.environment_tag_keys); criterion("Ambientes não produtivos", policy.nonproduction_values);
      notes.push("A instância estava ligada no momento da coleta. Isso não comprova que permaneceu ligada durante todo o período fora do expediente.");
      break;
    case "load_balancer_no_traffic":
      source = "Inventário AWS + Amazon CloudWatch";
      fact("Métrica", e.metric); fact("Total observado", e.metric_total); fact("Janela (dias)", e.lookback_days); fact("Amostras retornadas", e.datapoint_count);
      criterion("Limite de tráfego", e.metric === "ProcessedBytes" ? policy.maximum_processed_bytes : policy.maximum_requests);
      if (e.datapoint_count === 0) summary = "O CloudWatch não retornou amostras de tráfego no período. O coletor sinalizou o recurso, mas a ausência de tráfego não está confirmada.";
      if (e.datapoint_count === 0 || e.datapoint_count == null) notes.push("Ausência de amostras não confirma tráfego zero. Valide a disponibilidade das métricas antes de agir.");
      break;
    case "rds_nonprod_idle":
      source = "Inventário AWS + Amazon CloudWatch";
      fact("CPU média (%)", e.average_cpu_percent); fact("Máximo de conexões", e.maximum_connections); fact("Janela (dias)", e.lookback_days); fact("Classe", e.instance_class); fact("Tags observadas", e.tags);
      criterion("CPU média máxima (%)", policy.maximum_average_cpu_percent); criterion("Limite de conexões", policy.maximum_connections);
      criterion("Tags de ambiente", policy.environment_tag_keys); criterion("Ambientes não produtivos", policy.nonproduction_values);
      notes.push("A CPU é a média das médias diárias retornadas; conexões usam o maior máximo diário. As métricas disponíveis podem não cobrir toda a janela.");
      break;
    case "missing_required_tags":
      fact("Tags ausentes", e.missing_tags); fact("Tags encontradas", e.current_tags ?? e.tags);
      criterion("Tags obrigatórias", policy.required_tags);
      notes.push("A validação compara os nomes das tags sem diferenciar maiúsculas e minúsculas. Este achado não calcula economia financeira.");
      break;
  }
  if (e.demo === true) notes.unshift("Dados de demonstração; não representam uma coleta real na AWS.");
  if (e.policy_config == null && finding.rule_key !== "cost_growth_anomaly") notes.push("Esta varredura não registrou a configuração completa da política. Uma nova varredura acrescentará os critérios usados.");
  if (!["cost_growth_anomaly", "missing_required_tags"].includes(finding.rule_key)) {
    criterion("Economia mensal mínima (USD)", policy.minimum_monthly_savings_usd);
    if (Number(finding.estimated_monthly_savings) > 0) notes.push("A economia usa preços estimados configurados na política; valide o valor e a necessidade do recurso antes de agir.");
  }
  return { summary, facts, criteria, notes, source, contributors };
}
