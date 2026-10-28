"use client";

import { Check, Minus } from "lucide-react";
import { forwardRef, useEffect, useRef, type InputHTMLAttributes, type ReactNode } from "react";
import { iconDefaults } from "@/lib/iconography";
import styles from "./primitives.module.css";
import { cx, setRef } from "./utils";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: ReactNode;
  description?: ReactNode;
  indeterminate?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, description, indeterminate = false, className, disabled, ...props },
  forwardedRef,
) {
  const internalRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (internalRef.current) internalRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <label className={cx(styles.choiceLabel, className)}>
      <input
        {...props}
        ref={(node) => {
          internalRef.current = node;
          setRef(forwardedRef, node);
        }}
        type="checkbox"
        className={styles.choiceInput}
        data-aven-control-inner=""
        data-indeterminate={indeterminate || undefined}
        disabled={disabled}
        aria-checked={indeterminate ? "mixed" : props.checked}
      />
      <span className={styles.choiceBox} aria-hidden="true">
        <span className={styles.choiceIcon}>{indeterminate ? <Minus {...iconDefaults} /> : <Check {...iconDefaults} />}</span>
      </span>
      {(label || description) && (
        <span className={styles.choiceText}>
          {label && <span>{label}</span>}
          {description && <span className={styles.choiceDescription}>{description}</span>}
        </span>
      )}
    </label>
  );
});
