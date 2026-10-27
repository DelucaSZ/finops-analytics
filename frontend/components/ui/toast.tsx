"use client";

import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { createPortal } from "react-dom";
import { iconDefaults } from "@/lib/iconography";
import styles from "./feedback.module.css";

export type ToastVariant = "success" | "info" | "warning" | "danger";

export interface ToastInput {
  title: ReactNode;
  description?: ReactNode;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastRecord extends ToastInput {
  id: number;
  paused: boolean;
}

interface ToastContextValue {
  toast(input: ToastInput): number;
  dismiss(id: number): void;
}

const ToastContext = createContext<ToastContextValue | null>(null);
const toastIcons = { success: CheckCircle2, info: Info, warning: AlertTriangle, danger: AlertCircle } as const;
const DEFAULT_TOAST_DURATION = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const idRef = useRef(0);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback((input: ToastInput) => {
    const id = ++idRef.current;
    setToasts((current) => [...current, { ...input, id, paused: false }]);
    return id;
  }, []);

  const value = useMemo(() => ({ toast, dismiss }), [dismiss, toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {mounted && createPortal(
        <div className={styles.toastViewport} aria-live="polite" aria-relevant="additions removals">
          {toasts.map((item) => <ToastItem key={item.id} item={item} dismiss={dismiss} setToasts={setToasts} />)}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

function ToastItem({
  item,
  dismiss,
  setToasts,
}: {
  item: ToastRecord;
  dismiss(id: number): void;
  setToasts: Dispatch<SetStateAction<ToastRecord[]>>;
}) {
  const variant = item.variant ?? "info";
  const Icon = toastIcons[variant];

  useEffect(() => {
    if (item.paused) return;
    const timeout = window.setTimeout(() => dismiss(item.id), item.duration ?? DEFAULT_TOAST_DURATION);
    return () => window.clearTimeout(timeout);
  }, [dismiss, item.duration, item.id, item.paused]);

  return (
    <div
      className={styles.toast}
      data-variant={variant}
      role={variant === "danger" ? "alert" : "status"}
      onMouseEnter={() => setToasts((current) => current.map((toast) => toast.id === item.id ? { ...toast, paused: true } : toast))}
      onMouseLeave={() => setToasts((current) => current.map((toast) => toast.id === item.id ? { ...toast, paused: false } : toast))}
      onFocusCapture={() => setToasts((current) => current.map((toast) => toast.id === item.id ? { ...toast, paused: true } : toast))}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setToasts((current) => current.map((toast) => toast.id === item.id ? { ...toast, paused: false } : toast));
        }
      }}
    >
      <span className={styles.toastIcon} aria-hidden="true"><Icon {...iconDefaults} /></span>
      <span className={styles.toastContent}>
        <span className={styles.toastTitle}>{item.title}</span>
        {item.description && <span className={styles.toastDescription}>{item.description}</span>}
      </span>
      <button className={styles.toastDismiss} type="button" aria-label="Dispensar notificação" onClick={() => dismiss(item.id)}>
        <X {...iconDefaults} />
      </button>
    </div>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}
