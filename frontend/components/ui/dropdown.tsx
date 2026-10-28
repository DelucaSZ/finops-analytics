"use client";

import {
  createContext,
  forwardRef,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import styles from "./overlays.module.css";
import { cx } from "./utils";
import { useControllableState } from "./use-controllable-state";
import { positionDropdown, type DropdownPosition } from "./viewport-position";

interface DropdownContextValue {
  open: boolean;
  setOpen(open: boolean): void;
  contentId: string;
  triggerId: string;
  triggerRef: RefObject<HTMLButtonElement | null>;
  contentRef: RefObject<HTMLDivElement | null>;
}

const DropdownContext = createContext<DropdownContextValue | null>(null);

function useDropdown() {
  const context = useContext(DropdownContext);
  if (!context) throw new Error("Dropdown components must be used inside DropdownMenu");
  return context;
}

export interface DropdownMenuProps extends HTMLAttributes<HTMLDivElement> {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function DropdownMenu({ open, defaultOpen = false, onOpenChange, className, children, ...props }: DropdownMenuProps) {
  const [isOpen, setOpen] = useControllableState({ value: open, defaultValue: defaultOpen, onChange: onOpenChange });
  const baseId = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const closeAndRestoreFocus = () => {
      setOpen(false);
      triggerRef.current?.focus();
    };

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !contentRef.current?.contains(target)) setOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      closeAndRestoreFocus();
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, setOpen]);

  return (
    <DropdownContext.Provider
      value={{
        open: isOpen,
        setOpen,
        contentId: `${baseId}-content`,
        triggerId: `${baseId}-trigger`,
        triggerRef,
        contentRef,
      }}
    >
      <div ref={rootRef} className={cx(styles.dropdownRoot, className)} {...props}>{children}</div>
    </DropdownContext.Provider>
  );
}

export const DropdownMenuTrigger = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(function DropdownMenuTrigger(
  { onClick, className, children, type = "button", id, ...props },
  forwardedRef,
) {
  const { open, setOpen, contentId, triggerId, triggerRef } = useDropdown();
  return (
    <button
      {...props}
      id={id ?? triggerId}
      ref={(node) => {
        triggerRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) forwardedRef.current = node;
      }}
      type={type}
      className={cx(styles.dropdownTrigger, className)}
      aria-haspopup="menu"
      aria-expanded={open}
      aria-controls={open ? contentId : undefined}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) setOpen(!open);
      }}
    >
      {children}
    </button>
  );
});

export interface DropdownMenuContentProps extends HTMLAttributes<HTMLDivElement> {
  "aria-label"?: string;
}

export function DropdownMenuContent({ className, children, onKeyDown, "aria-label": ariaLabel, ...props }: DropdownMenuContentProps) {
  const { open, setOpen, contentId, triggerId, triggerRef, contentRef } = useDropdown();
  const [mounted, setMounted] = useState(false);
  const [position, setPosition] = useState<DropdownPosition | null>(null);

  useEffect(() => setMounted(true), []);

  useLayoutEffect(() => {
    if (!open || !mounted) return;
    const updatePosition = () => {
      const trigger = triggerRef.current;
      const content = contentRef.current;
      if (trigger && content) setPosition(positionDropdown(trigger.getBoundingClientRect(), content.getBoundingClientRect()));
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [children, contentRef, mounted, open, triggerRef]);

  useEffect(() => {
    if (!open || !mounted) return;
    const first = contentRef.current?.querySelector<HTMLButtonElement>("[role='menuitem']:not(:disabled)");
    first?.focus();
  }, [contentRef, mounted, open]);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      {...props}
      ref={contentRef}
      id={contentId}
      role="menu"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabel ? undefined : triggerId}
      className={cx(styles.dropdownContent, className)}
      data-positioned={position ? "true" : "false"}
      data-side={position?.side}
      style={position ? { top: position.top, left: position.left, maxBlockSize: position.maxBlockSize } : undefined}
      onKeyDown={(event) => {
        onKeyDown?.(event);
        if (event.defaultPrevented) return;
        const items = Array.from(contentRef.current?.querySelectorAll<HTMLButtonElement>("[role='menuitem']:not(:disabled)") ?? []);
        const index = items.indexOf(document.activeElement as HTMLButtonElement);
        if (event.key === "Escape") {
          event.preventDefault();
          setOpen(false);
          triggerRef.current?.focus();
        } else if (event.key === "ArrowDown") {
          event.preventDefault();
          items[(index + 1 + items.length) % items.length]?.focus();
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          items[(index - 1 + items.length) % items.length]?.focus();
        } else if (event.key === "Home") {
          event.preventDefault();
          items.at(0)?.focus();
        } else if (event.key === "End") {
          event.preventDefault();
          items.at(-1)?.focus();
        }
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

export interface DropdownMenuItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  danger?: boolean;
  icon?: ReactNode;
}

export const DropdownMenuItem = forwardRef<HTMLButtonElement, DropdownMenuItemProps>(function DropdownMenuItem(
  { danger = false, icon, onClick, className, children, type = "button", ...props },
  ref,
) {
  const { setOpen, triggerRef } = useDropdown();
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      role="menuitem"
      className={cx(styles.dropdownItem, className)}
      data-danger={danger || undefined}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) {
          setOpen(false);
          triggerRef.current?.focus();
        }
      }}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      <span>{children}</span>
    </button>
  );
});

export function DropdownMenuSeparator(props: HTMLAttributes<HTMLHRElement>) {
  return <hr className={styles.dropdownSeparator} role="separator" {...props} />;
}