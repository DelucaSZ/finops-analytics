"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { X } from "lucide-react";
import { rejectionRequiresNote } from "@/lib/opportunity-query.mjs";

export type OpportunityDecisionAction = "treat" | "reject" | "reopen";

const rejectionReasons = [
  ["FALSE_POSITIVE", "Falso positivo"],
  ["OPERATIONAL_EXCEPTION", "Exceção operacional"],
  ["ACCEPTABLE_COST", "Custo aceitável"],
  ["RESOURCE_REQUIRED", "Recurso necessário"],
  ["RISK_ACCEPTED", "Risco aceito"],
  ["OTHER", "Outro"],
] as const;

const copy: Record<OpportunityDecisionAction, { title: string; submit: string; hint: string }> = {
  treat: {
    title: "Marcar como tratada",
    submit: "Marcar como tratada",
    hint: "Registre uma observação opcional sobre o tratamento realizado.",
  },
  reject: {
    title: "Rejeitar oportunidade",
    submit: "Rejeitar",
    hint: "Selecione o motivo da decisão. O histórico será preservado.",
  },
  reopen: {
    title: "Reabrir oportunidade",
    submit: "Reabrir",
    hint: "A oportunidade voltará para Abertas sem apagar decisões anteriores.",
  },
};

type Props = {
  action: OpportunityDecisionAction;
  count: number;
  saving: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (payload: { reason?: string; note?: string }) => Promise<void> | void;
};

export function OpportunityDecisionDialog({ action, count, saving, error, onClose, onSubmit }: Props) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [validation, setValidation] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const text = copy[action];

  useEffect(() => {
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, saving]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation("");
    if (action === "reject" && !reason) {
      setValidation("Selecione um motivo para rejeitar.");
      return;
    }
    if (action === "reject" && rejectionRequiresNote(reason) && !note.trim()) {
      setValidation("A observação é obrigatória quando o motivo é Outro.");
      return;
    }
    await onSubmit({ reason: reason || undefined, note: note.trim() || undefined });
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !saving) onClose();
    }}>
      <section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="decision-dialog-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">DECISÃO OPERACIONAL</span>
            <h2 id="decision-dialog-title">{text.title}</h2>
            <p>{count > 1 ? `${count} oportunidades selecionadas. ` : ""}{text.hint}</p>
          </div>
          <button ref={closeRef} className="icon-button" type="button" aria-label="Fechar" disabled={saving} onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit}>
          {action === "reject" && (
            <label className="dialog-field">
              Motivo
              <select value={reason} disabled={saving} onChange={(event) => setReason(event.target.value)} required>
                <option value="">Selecione um motivo</option>
                {rejectionReasons.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </label>
          )}
          <label className="dialog-field">
            Observação {action === "reject" && rejectionRequiresNote(reason) ? "*" : "(opcional)"}
            <textarea
              value={note}
              disabled={saving}
              rows={5}
              maxLength={4000}
              placeholder={action === "reopen" ? "Contexto da reabertura" : "Contexto para auditoria"}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {(validation || error) && <p className="dialog-error" role="alert">{validation || error}</p>}
          <div className="dialog-actions">
            <button className="button ghost" type="button" disabled={saving} onClick={onClose}>Cancelar</button>
            <button className="button primary" type="submit" disabled={saving}>{saving ? "Aplicando…" : text.submit}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
