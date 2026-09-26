"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { GitCompareArrows } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate } from "@/lib/api";
import type { CollectionComparisonRun, CollectionRun } from "@/lib/types";
import styles from "../collection.module.css";

function statusValue(status: string) {
  if (status === "SUCCESS") return "completed";
  return status.toLowerCase();
}

export default function CollectionRunDetailPage() {
  const params = useParams<{ collectionId: string }>();
  const collectionId = params.collectionId;
  const [run, setRun] = useState<CollectionRun | null>(null);
  const [options, setOptions] = useState<CollectionComparisonRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      api<CollectionRun>(`/collections/${collectionId}`),
      api<CollectionComparisonRun[]>(`/collections/${collectionId}/comparison-options?limit=100`),
    ])
      .then(([runData, optionData]) => {
        if (!active) return;
        setRun(runData);
        setOptions(optionData);
        setError("");
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar a coleta.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [collectionId]);

  if (loading) return <div className={styles.state}>Carregando coleta…</div>;
  if (error || !run) {
    return (
      <div className={styles.state} role="alert">
        {error || "CollectionRun não encontrado."}
      </div>
    );
  }

  const previous = options[0];
  const canCompare = run.status === "SUCCESS";

  return (
    <>
      <PageHeader
        eyebrow="COLLECTION RUN"
        title={`Coleta ${run.id.slice(0, 8)}`}
        description="Registro auditável da execução de coleta e ponto de entrada para comparação temporal."
        actions={
          <div className={styles.headerActions}>
            <Link className="button ghost" href="/scans">
              Voltar às execuções
            </Link>
            {canCompare && previous && (
              <Link
                className="button primary"
                href={`/collections/${run.id}/compare?baseline_id=${previous.id}`}
              >
                <GitCompareArrows size={17} />
                Comparar com coleta anterior
              </Link>
            )}
          </div>
        }
      />

      <section className={styles.runGrid}>
        <article className={styles.runCard}>
          <span>Provider</span>
          <strong>{run.provider.toUpperCase()}</strong>
        </article>
        <article className={styles.runCard}>
          <span>Conta</span>
          <strong>{run.account_id}</strong>
        </article>
        <article className={styles.runCard}>
          <span>Início</span>
          <strong>{formatDate(run.started_at)}</strong>
        </article>
        <article className={styles.runCard}>
          <span>Conclusão</span>
          <strong>{formatDate(run.finished_at)}</strong>
        </article>
        <article className={styles.runCard}>
          <span>Status</span>
          <StatusBadge value={statusValue(run.status)} />
        </article>
        <article className={styles.runCard}>
          <span>Rules/analyzer version</span>
          <strong>{run.analyzer_version || "Não registrada"}</strong>
        </article>
        <article className={styles.runCard}>
          <span>Oportunidades detectadas</span>
          <strong>{run.opportunities_found}</strong>
        </article>
        <article className={styles.runCard}>
          <span>Recursos analisados</span>
          <strong>{run.resources_analyzed || "Não instrumentado"}</strong>
        </article>
      </section>

      <section className={`panel ${styles.actionsPanel}`}>
        <div>
          <span className="eyebrow">INVESTIGAÇÃO</span>
          <h2>Dados desta coleta</h2>
          <p>
            A comparação usa as OpportunityObservations persistidas nesta execução. O lifecycle
            humano das oportunidades é exibido separadamente e não altera a classificação do diff.
          </p>
        </div>
        <div className={styles.headerActions}>
          <Link
            className="button ghost"
            href={`/opportunities?collection_run_id=${encodeURIComponent(run.id)}`}
          >
            Ver oportunidades desta coleta
          </Link>
          {canCompare && (
            <Link className="button primary" href={`/collections/${run.id}/compare`}>
              Comparar
            </Link>
          )}
        </div>
      </section>

      {!canCompare && (
        <div className={`alert error ${styles.notice}`}>
          Apenas CollectionRuns concluídos com SUCCESS podem participar da comparação temporal.
        </div>
      )}

      {canCompare && !previous && (
        <div className={`alert ${styles.notice}`}>
          Esta é a primeira coleta bem-sucedida disponível para este provider e conta. Não existe
          uma coleta anterior para comparação.
        </div>
      )}

      {run.error_detail && (
        <div className={`alert error ${styles.notice}`}>
          <strong>Erro registrado:</strong> {run.error_detail}
        </div>
      )}
    </>
  );
}
