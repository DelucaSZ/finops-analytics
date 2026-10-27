"use client";

import { forwardRef, useId, type ButtonHTMLAttributes, type ReactNode } from "react";
import styles from "./primitives.module.css";
import { cx } from "./utils";
import { useControllableState } from "./use-controllable-state";

export interface SwitchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "role"> {
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  label?: ReactNode;
  description?: ReactNode;
}

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(function Switch(
  {
    checked,
    defaultChecked = false,
    onCheckedChange,
    label,
    description,
    disabled,
    className,
    onClick,
    id,
    "aria-label": ariaLabel,
    "aria-labelledby": ariaLabelledBy,
    "aria-describedby": ariaDescribedBy,
    type = "button",
    ...props
  },
  ref,
) {
  const [isChecked, setChecked] = useControllableState({ value: checked, defaultValue: defaultChecked, onChange: onCheckedChange });
  const generatedId = useId();
  const controlId = id ?? `${generatedId}-control`;
  const labelId = label ? `${generatedId}-label` : undefined;
  const descriptionId = description ? `${generatedId}-description` : undefined;

  return (
    <span className={cx(styles.switchRoot, className)}>
      <button
        {...props}
        id={controlId}
        ref={ref}
        type={type}
        role="switch"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy ?? (!ariaLabel ? labelId : undefined)}
        aria-describedby={ariaDescribedBy ?? descriptionId}
        aria-checked={isChecked}
        disabled={disabled}
        className={styles.switchControl}
        data-state={isChecked ? "checked" : "unchecked"}
        onClick={(event) => {
          onClick?.(event);
          if (!event.defaultPrevented && !disabled) setChecked(!isChecked);
        }}
      >
        <span className={styles.switchThumb} aria-hidden="true" />
      </button>
      {(label || description) && (
        <span className={styles.switchText}>
          {label && <label id={labelId} htmlFor={controlId} className={styles.switchLabel}>{label}</label>}
          {description && <span id={descriptionId} className={styles.switchDescription}>{description}</span>}
        </span>
      )}
    </span>
  );
});
