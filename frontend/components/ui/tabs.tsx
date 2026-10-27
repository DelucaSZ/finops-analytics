"use client";

import {
  createContext,
  useContext,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import styles from "./overlays.module.css";
import { cx } from "./utils";
import { useControllableState } from "./use-controllable-state";

interface TabsContextValue {
  value: string;
  setValue(value: string): void;
  baseId: string;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabs() {
  const context = useContext(TabsContext);
  if (!context) throw new Error("Tabs components must be used inside Tabs");
  return context;
}

export interface TabsProps extends HTMLAttributes<HTMLDivElement> {
  value?: string;
  defaultValue: string;
  onValueChange?: (value: string) => void;
}

export function Tabs({ value, defaultValue, onValueChange, className, children, ...props }: TabsProps) {
  const [activeValue, setValue] = useControllableState({ value, defaultValue, onChange: onValueChange });
  const baseId = useId();
  return (
    <TabsContext.Provider value={{ value: activeValue, setValue, baseId }}>
      <div className={cx(styles.tabsRoot, className)} {...props}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, onKeyDown, ...props }: HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement | null>(null);
  return (
    <div
      {...props}
      ref={ref}
      role="tablist"
      className={cx(styles.tabsList, className)}
      onKeyDown={(event) => {
        onKeyDown?.(event);
        if (event.defaultPrevented) return;
        const tabs = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>("[role='tab']:not(:disabled)") ?? []);
        const index = tabs.indexOf(document.activeElement as HTMLButtonElement);
        let nextIndex = index;
        if (event.key === "ArrowRight") nextIndex = (index + 1 + tabs.length) % tabs.length;
        else if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
        else if (event.key === "Home") nextIndex = 0;
        else if (event.key === "End") nextIndex = tabs.length - 1;
        else return;
        event.preventDefault();
        tabs[nextIndex]?.focus();
        tabs[nextIndex]?.click();
      }}
    />
  );
}

export interface TabsTriggerProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
}

export function TabsTrigger({ value, className, children, type = "button", ...props }: TabsTriggerProps) {
  const { value: activeValue, setValue, baseId } = useTabs();
  const selected = activeValue === value;
  return (
    <button
      {...props}
      type={type}
      id={`${baseId}-tab-${value}`}
      role="tab"
      className={cx(styles.tabTrigger, className)}
      aria-selected={selected}
      aria-controls={`${baseId}-panel-${value}`}
      tabIndex={selected ? 0 : -1}
      onClick={(event) => {
        props.onClick?.(event);
        if (!event.defaultPrevented) setValue(value);
      }}
    >
      {children}
    </button>
  );
}

export interface TabsContentProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
  children: ReactNode;
}

export function TabsContent({ value, className, children, ...props }: TabsContentProps) {
  const { value: activeValue, baseId } = useTabs();
  if (activeValue !== value) return null;
  return (
    <div
      {...props}
      id={`${baseId}-panel-${value}`}
      role="tabpanel"
      aria-labelledby={`${baseId}-tab-${value}`}
      className={cx(styles.tabPanel, className)}
    >
      {children}
    </div>
  );
}
