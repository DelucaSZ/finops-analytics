"use client";

import Link from "next/link";
import { Suspense, useMemo } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { formatDate } from "@/lib/api";
import { formatAccountLabel, formatNumber, providerLabel } from "@/lib/cloud.mjs";
import {
  COLLECTION_DISCOVERY_LABELS,
  COLLECTION_DISCOVERY_TYPES,
} from "@/lib/collection-query.mjs";
import { cachePolicy } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";

type DiscoveryType =
  | "observed"
  | "first_seen"
  | "new_vs_previous"
  | "reappeared"
  | "continued"
  | "no_longer_detected";

type RunOpportunity = {
  id: string;
  provider: string;
  account_id: string;
  rule_key: string;
  service: string;
  region: string | null;
  resource_id: string;
  resource_name: string | null;
  resource_type: string | null;
  title: string;
  severity: string;
  status: string;
  presence_status: string;
  first_seen_at: string;
  last_seen_at: string;
  archived_at: string | null;
};

type RunOpportunityPage = {
  collection_run_id: string;
  baseline_run_id: string | null;
  comparable: boolean;
  reason: string | null;
  discovery_type: DiscoveryType;
  items: RunOpportunity[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export default function CollectionOpportunitiesPage() {
  return (
    <Suspense fallback={<p role="status">Carregando oportunidades…</p>}>
      <CollectionOpportunitiesContent />
    </Suspense>
  );
}

function CollectionOpportunitiesContent() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const requestedType = searchParams.get("discovery_type") || "observed";
  const discoveryType = (
    COLLECTION_DISCOVERY_TYPES.includes(requestedType) ? requestedType : "observed"
  ) as DiscoveryType;
  const page = Math.max(1, Number(searchParams.get("page") || 1) || 1);
  const provider = searchParams.get("provider") || "";
  const accountId = searchParams.get("account_id") || "";
  const apiQuery = useMemo(() => {
    const params = new URLSearchParams({
      discovery_type: discoveryType,
      include_archived: "true",
      page: String(page),
      page_size: "50",
    });
    return params.toString();
  }, [discoveryType, page]);

  const request = useApiQuery<RunOpportunityPage>({
    key: ["collections", collectionId, "opportunities", discoveryType, page, "all-archive-states"],
    path: `/collections/${encodeURIComponent(collectionId)}/opportunities?${apiQuery}`,
    ...cachePolicy.operational,
    keepPreviousData: true,
  });
  const data = request.data;
  const label = COLLECTION_DISCOVERY_LABELS[discoveryType] || discoveryType;

  function changePage(next: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(next));
    router.replace(`/opportunities/collection/${encodeURIComponent(collectionId)}?${params.toString()}`, { scroll: false });
  }

  return (
    <>
      <PageHeader
        eyebrow="OPORTUNIDADES · INVESTIGAÇÃO DE COLETA"
        title={label}
        description="Visão histórica/técnica baseada nas OpportunityObservations da CollectionRun, sem forçar status atual ou estado de arquivamento."
      />
      <div className="collection-toolbar">
        <Link className="button ghost" href={`/collections/${encodeURIComponent(collectionId)}`}>← Voltar à coleta</Link>
        <Link className="button ghost" href="/opportunities">Abrir backlog atual</Link>
      </div>

      <section className="panel" aria-busy={request.isLoading || request.isFetching}>
        <div className="active-filter-summary" aria-label="Filtro aplicado">
          <span>Coleta: {collectionId.slice(0, 8)}</span>
          <span>Classificação: {label}</span>
          {provider && <span>Cloud: {providerLabel(provider)}</span>}
          {accountId && <span>Conta: {formatAccountLabel(null, accountId)}</span>}
        </div>
        <p className="collection-note">
          Esta investigação pode incluir oportunidades atualmente tratadas, rejeitadas ou arquivadas. O estado operacional não é alterado.
        </p>

        {request.error && (
          <div className="alert error" role="alert">
            Não foi possível carregar este subconjunto da coleta.
            <button className="button ghost" onClick={() => void request.refetch()}>Tentar novamente</button>
          </div>
        )}
        {(request.isLoading || request.isFetching) && <p role="status">Carregando oportunidades…</p>}
        {data?.reason === "NO_BASELINE" && discoveryType !== "observed" && discoveryType !== "first_seen" && (
          <div className="alert" role="status">Sem coleta anterior comparável; esta classificação não é calculada para a primeira coleta.</div>
        )}
        {(data?.reason === "TARGET_OBSERVATIONS_EXPIRED" || data?.reason === "BASELINE_OBSERVATIONS_EXPIRED") && (
          <div className="alert" role="status">Os detalhes por oportunidade necessários para esta investigação expiraram pela política de retenção.</div>
        )}
        {data?.reason === "TARGET_NOT_SUCCESSFUL" && !["observed", "first_seen"].includes(discoveryType) && (
          <div className="alert" role="status">A coleta não foi concluída com sucesso; comparações relativas não são tratadas como resultado definitivo.</div>
        )}

        {data && (
          <div className="panel-heading collection-toolbar">
            <h2>{formatNumber(data.total)} oportunidade(s)</h2>
            {data.baseline_run_id && <span>Baseline: <code>{data.baseline_run_id.slice(0, 8)}</code></span>}
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="data-table-wrap" tabIndex={0} role="region" aria-label={label}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Oportunidade</th><th>Cloud / conta</th><th>Serviço / região</th><th>Status atual</th><th>Primeira / última detecção</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link className="collection-link" href={`/opportunities?opportunity_id=${encodeURIComponent(item.id)}`}>{item.title}</Link>
                      <span>{item.resource_name || item.resource_id}</span>
                      <code>{item.rule_key}</code>
                    </td>
                    <td>{providerLabel(item.provider)}<span>{item.account_id}</span></td>
                    <td>{item.service}<span>{item.region || "Global"}</span></td>
                    <td>{item.status}{item.archived_at ? <span>Arquivada</span> : null}</td>
                    <td>{formatDate(item.first_seen_at)}<span>{formatDate(item.last_seen_at)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && !request.isLoading && data.items.length === 0 && !data.reason && (
          <div className="empty-table">Nenhuma oportunidade corresponde a esta classificação.</div>
        )}
        {data && (
          <div className="collection-toolbar collection-pagination">
            <span>Página {data.page} de {data.total_pages || 1}</span>
            <button className="button ghost" disabled={data.page <= 1} onClick={() => changePage(data.page - 1)}>Anterior</button>
            <button className="button ghost" disabled={data.total_pages === 0 || data.page >= data.total_pages} onClick={() => changePage(data.page + 1)}>Próxima</button>
          </div>
        )}
      </section>
    </>
  );
}
