"use client";

import { X } from "lucide-react";
import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  type DialogHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { iconDefaults } from "@/lib/iconography";
import { Button, type ButtonProps } from "./button";
import styles from "./overlays.module.css";
import { cx } from "./utils";
import { useControllableState } from "./use-controllable-state";

interface DialogContextValue {
  open: boolean;
  setOpen(open: boolean): void;
  titleId: string;
  descriptionId: string;
}

const DialogContext = createContext<DialogContextValue | null>(null);

function useDialog() {
  const context = useContext(DialogContext);
  if (!context) throw new Error("Dialog components must be used inside Dialog");
  return context;
}

export interface DialogProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}

export function Dialog({ open, defaultOpen = false, onOpenChange, children }: DialogProps) {
  const [isOpen, setOpen] = useControllableState({ value: open, defaultValue: defaultOpen, onChange: onOpenChange });
  const baseId = useId();
  return (
    <DialogContext.Provider value={{ open: isOpen, setOpen, titleId: `${baseId}-title`, descriptionId: `${baseId}-description` }}>
      {children}
    </DialogContext.Provider>
  );
}

export function DialogTrigger(props: ButtonProps) {
  const { setOpen } = useDialog();
  return <Button type="button" {...props} onClick={(event) => { props.onClick?.(event); if (!event.defaultPrevented) setOpen(true); }} />;
}

export function DialogContent({ className, children, onCancel, onClose, onClick, ...props }: DialogHTMLAttributes<HTMLDialogElement>) {
  const { open, setOpen, titleId, descriptionId } = useDialog();
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      {...props}
      ref={ref}
      className={cx(styles.dialog, className)}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        onCancel?.(event);
        if (!event.defaultPrevented) setOpen(false);
      }}
      onClose={(event) => {
        onClose?.(event);
        setOpen(false);
      }}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented && event.target === event.currentTarget) setOpen(false);
      }}
    >
      <div className={styles.dialogInner}>
        {children}
        <button type="button" className={styles.dialogClose} aria-label="Fechar diálogo" onClick={() => setOpen(false)}>
          <X {...iconDefaults} />
        </button>
      </div>
    </dialog>
  );
}

export function DialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx(styles.dialogHeader, className)} {...props} />;
}

export function DialogTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  const { titleId } = useDialog();
  return <h2 id={titleId} className={cx(styles.dialogTitle, className)} {...props} />;
}

export function DialogDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  const { descriptionId } = useDialog();
  return <p id={descriptionId} className={cx(styles.dialogDescription, className)} {...props} />;
}

export function DialogFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx(styles.dialogFooter, className)} {...props} />;
}

export function DialogClose({ children = "Fechar", ...props }: ButtonProps) {
  const { setOpen } = useDialog();
  return <Button type="button" variant="secondary" {...props} onClick={(event) => { props.onClick?.(event); if (!event.defaultPrevented) setOpen(false); }}>{children}</Button>;
}
