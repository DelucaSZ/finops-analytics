"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CollectionComparisonRun } from "@/lib/types";

export function CollectionComparisonActions({ run }: { run: { id: string; status: string } }) {
  const [options, setOptions] = useState<CollectionComparisonRun[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setOptions(null); setError(false);
    if (run.status === "SUCCESS") {
      api<CollectionComparisonRun[]>(`/collections/${encodeURIComponent(run.id)}/comparison-options?limit=100`, { signal: controller.signal })
        .then(value => { if (!controller.signal.aborted) setOptions(value); })
        .catch(() => { if (!controller.signal.aborted) setError(true); });
    }
    return () => controller.abort();
  }, [run.id, run.status]);
  if (run.status !== "SUCCESS") return null;
  return <div aria-label="Comparação de coletas">
    <div className="collection-toolbar">
      <Link className="button ghost" href={`/collections/${encodeURIComponent(run.id)}/compare`}>Comparar</Link>
      {options?.[0] && <Link className="button primary" href={`/collections/${encodeURIComponent(run.id)}/compare?baseline_id=${encodeURIComponent(options[0].id)}`}>Comparar com coleta anterior</Link>}
    </div>
    {options?.length === 0 && <p>Esta é a primeira coleta bem-sucedida disponível para este provider e conta. Não existe uma coleta anterior para comparação.</p>}
    {error && <p role="status">Não foi possível carregar as sugestões. Abra Comparar para tentar novamente.</p>}
  </div>;
}
