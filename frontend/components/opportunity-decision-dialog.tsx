"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
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

type Props = {
  action: OpportunityDecisionAction;
  count: number;
  saving: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (payload: { reason?: string; note?: string }) => Promise<void> | void;
};

export function OpportunityDecisionDialog({ action, count, saving, error, onClose, onSubmit }: Props) {
  const t = useTranslations("opportunities.decision");
  const rejectionReasons = ["FALSE_POSITIVE","OPERATIONAL_EXCEPTION","ACCEPTABLE_COST","RESOURCE_REQUIRED","RISK_ACCEPTED","OTHER"].map(value => ({value, label: t(`reason.${value}`)}));
  const copy = {
    treat:{title:t("treatTitle"), submit:t("treatTitle"), hint:t("treatHint")},
    reject:{title:t("rejectTitle"), submit:t("rejectButton"), hint:t("rejectHint")},
    reopen:{title:t("reopenTitle"), submit:t("reopenButton"), hint:t("reopenHint")},
  };
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [validation, setValidation] = useState("");
  const text = copy[action];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation("");
    if (action === "reject" && !reason) {
      setValidation(t("reasonMissing"));
      return;
    }
    if (action === "reject" && rejectionRequiresNote(reason) && !note.trim()) {
      setValidation(t("noteRequired"));
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
              {count > 1 ? `${t("selected", {count})} ` : ""}{text.hint}
            </DialogDescription>
          </DialogHeader>

          {action === "reject" ? (
            <Select
              label={t("reasonLabel")}
              value={reason}
              disabled={saving}
              required
              placeholder={t("reasonPlaceholder")}
              options={rejectionReasons}
              onChange={(event) => setReason(event.target.value)}
            />
          ) : null}

          <Textarea
            label={`${t("note")} ${action === "reject" && rejectionRequiresNote(reason) ? "*" : `(${t("optional")})`}`}
            value={note}
            disabled={saving}
            rows={5}
            maxLength={4000}
            placeholder={action === "reopen" ? t("reopenContext") : t("auditContext")}
            onChange={(event) => setNote(event.target.value)}
          />

          {validation || error ? <Alert variant="danger" title={t("failure")} description={validation || error} /> : null}

          <DialogFooter>
            <Button variant="secondary" type="button" disabled={saving} onClick={onClose}>{t("cancel")}</Button>
            <Button variant={action === "reject" ? "danger" : "primary"} type="submit" loading={saving}>
              {text.submit}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
