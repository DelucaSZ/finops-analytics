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

interface DrawerContextValue {
  open: boolean;
  setOpen(open: boolean): void;
  titleId: string;
  descriptionId: string;
}

const DrawerContext = createContext<DrawerContextValue | null>(null);

function useDrawer() {
  const context = useContext(DrawerContext);
  if (!context) throw new Error("Drawer components must be used inside Drawer");
  return context;
}

export interface DrawerProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}

export function Drawer({ open, defaultOpen = false, onOpenChange, children }: DrawerProps) {
  const [isOpen, setOpen] = useControllableState({ value: open, defaultValue: defaultOpen, onChange: onOpenChange });
  const baseId = useId();
  return (
    <DrawerContext.Provider value={{ open: isOpen, setOpen, titleId: `${baseId}-title`, descriptionId: `${baseId}-description` }}>
      {children}
    </DrawerContext.Provider>
  );
}

export function DrawerTrigger(props: ButtonProps) {
  const { setOpen } = useDrawer();
  return <Button {...props} onClick={(event) => { props.onClick?.(event); if (!event.defaultPrevented) setOpen(true); }} />;
}

export interface DrawerContentProps extends DialogHTMLAttributes<HTMLDialogElement> {
  side?: "left" | "right";
}

export function DrawerContent({ side = "right", className, children, onCancel, onClose, onClick, ...props }: DrawerContentProps) {
  const { open, setOpen, titleId, descriptionId } = useDrawer();
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const drawer = ref.current;
    if (!drawer) return;
    if (open && !drawer.open) drawer.showModal();
    if (!open && drawer.open) drawer.close();
  }, [open]);

  return (
    <dialog
      {...props}
      ref={ref}
      className={cx(styles.drawer, className)}
      data-side={side}
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
      <div className={styles.drawerInner}>
        {children}
        <button type="button" className={styles.drawerClose} aria-label="Fechar painel" onClick={() => setOpen(false)}>
          <X {...iconDefaults} />
        </button>
      </div>
    </dialog>
  );
}

export function DrawerHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx(styles.drawerHeader, className)} {...props} />;
}

export function DrawerTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  const { titleId } = useDrawer();
  return <h2 id={titleId} className={cx(styles.drawerTitle, className)} {...props} />;
}

export function DrawerDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  const { descriptionId } = useDrawer();
  return <p id={descriptionId} className={cx(styles.drawerDescription, className)} {...props} />;
}

export function DrawerFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx(styles.drawerFooter, className)} {...props} />;
}

export function DrawerClose({ children = "Fechar", ...props }: ButtonProps) {
  const { setOpen } = useDrawer();
  return <Button variant="secondary" {...props} onClick={(event) => { props.onClick?.(event); if (!event.defaultPrevented) setOpen(false); }}>{children}</Button>;
}
