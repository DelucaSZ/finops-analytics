"use client";

import { X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { patchOpportunityUrl } from "@/lib/opportunity-query.mjs";

const labels: Record<string, string> = {
  new_vs_previous: "Novas vs coleta anterior",
  first_seen: "Identificadas pela primeira vez",
  reappeared: "Reapareceram",
};

export function OpportunityComparisonContext() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const comparisonContext = searchParams.get("comparison_context");

  if (pathname !== "/opportunities" || !comparisonContext) return null;

  const comparisonKind = searchParams.get("comparison_kind") || "new_vs_previous";
  const provider = searchParams.get("provider");
  const accountId = searchParams.get("account_id");
  const scope = accountId
    ? `Conta ${accountId}${provider ? ` · ${provider.toUpperCase()}` : ""}`
    : provider
      ? `${provider.toUpperCase()} · todas as contas`
      : "Todas as clouds · todas as contas";

  function clearComparison() {
    const next = patchOpportunityUrl(searchParams, { discovery_type: null });
    router.replace(`${pathname}${next.size ? `?${next.toString()}` : ""}`, { scroll: false });
  }

  return (
    <section className="alert" aria-label="Contexto de comparação ativo">
      <div>
        <strong>Filtro ativo: {labels[comparisonKind] || labels.new_vs_previous}</strong>
        <span> · {scope}. Comparação calculada com as coletas selecionadas no Dashboard.</span>
      </div>
      <button
        className="button ghost"
        type="button"
        onClick={clearComparison}
        aria-label="Remover filtro de comparação"
      >
        <X size={15} aria-hidden="true" />
        Remover comparação
      </button>
    </section>
  );
}
