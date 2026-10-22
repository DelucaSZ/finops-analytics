"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CollectionOpportunityInvestigation } from "@/components/collection-opportunity-investigation";
import { api } from "@/lib/api";
import type { CollectionComparisonRun } from "@/lib/types";

type InvestigationRun = {
  id: string;
  status: string;
  provider: string;
  account_id: string;
};

export function CollectionComparisonActions({ run }: { run: InvestigationRun }) {
  const [options, setOptions] = useState<CollectionComparisonRun[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setOptions(null);
    setError(false);
    if (run.status === "SUCCESS") {
      api<CollectionComparisonRun[]>(
        `/collections/${encodeURIComponent(run.id)}/comparison-options?limit=100`,
        { signal: controller.signal },
      )
        .then((value) => {
          if (!controller.signal.aborted) setOptions(value);
        })
        .catch(() => {
          if (!controller.signal.aborted) setError(true);
        });
    }
    return () => controller.abort();
  }, [run.id, run.status]);

  return (
    <div aria-label="Comparação de coletas">
      {run.status === "SUCCESS" && (
        <div className="collection-toolbar">
          <Link className="button ghost" href={`/collections/${encodeURIComponent(run.id)}/compare`}>
            Comparar
          </Link>
          {options?.[0] && (
            <Link
              className="button primary"
              href={`/collections/${encodeURIComponent(run.id)}/compare?baseline_id=${encodeURIComponent(options[0].id)}`}
            >
              Comparar com coleta anterior
            </Link>
          )}
        </div>
      )}
      {run.status === "SUCCESS" && options?.length === 0 && (
        <p>Esta é a primeira coleta bem-sucedida disponível para este provider e conta. Não existe uma coleta anterior para comparação.</p>
      )}
      {error && <p role="status">Não foi possível carregar as sugestões. Abra Comparar para tentar novamente.</p>}
      <CollectionOpportunityInvestigation run={run} />
    </div>
  );
}
