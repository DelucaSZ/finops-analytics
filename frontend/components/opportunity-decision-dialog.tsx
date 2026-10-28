"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  Textarea,
} from "@/components/ui";
import { rejectionRequiresNote } from "@/lib/opportunity-query.mjs";
import styles from "./opportunity-dialog.module.css";

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
  const text = copy[action];

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
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
      <DialogContent onCancel={(event) => { if (saving) event.preventDefault(); }}>
        <form className={styles.form} onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{text.title}</DialogTitle>
            <DialogDescription>
              {count > 1 ? `${count} oportunidades selecionadas. ` : ""}{text.hint}
            </DialogDescription>
          </DialogHeader>

          {action === "reject" ? (
            <Select
              label="Motivo"
              value={reason}
              disabled={saving}
              required
              placeholder="Selecione um motivo"
              options={rejectionReasons.map(([value, label]) => ({ value, label }))}
              onChange={(event) => setReason(event.target.value)}
            />
          ) : null}

          <Textarea
            label={`Observação ${action === "reject" && rejectionRequiresNote(reason) ? "*" : "(opcional)"}`}
            value={note}
            disabled={saving}
            rows={5}
            maxLength={4000}
            placeholder={action === "reopen" ? "Contexto da reabertura" : "Contexto para auditoria"}
            onChange={(event) => setNote(event.target.value)}
          />

          {validation || error ? <Alert variant="danger" title="Não foi possível concluir a decisão" description={validation || error} /> : null}

          <DialogFooter>
            <Button variant="secondary" type="button" disabled={saving} onClick={onClose}>Cancelar</Button>
            <Button variant={action === "reject" ? "danger" : "primary"} type="submit" loading={saving}>
              {text.submit}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
