import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";
import styles from "./primitives.module.css";
import { Field, FieldDescription, FieldError, FieldLabel } from "./field";
import { cx } from "./utils";
import type { ControlSize } from "./button";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  leadingIcon?: ReactNode;
  trailingAction?: ReactNode;
  controlSize?: ControlSize;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    id,
    label,
    helperText,
    error,
    leadingIcon,
    trailingAction,
    controlSize = "md",
    className,
    disabled,
    readOnly,
    "aria-describedby": ariaDescribedBy,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const helperId = helperText ? `${inputId}-description` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [ariaDescribedBy, helperId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <Field>
      {label && <FieldLabel htmlFor={inputId}>{label}</FieldLabel>}
      <div
        className={styles.inputShell}
        data-size={controlSize}
        data-disabled={disabled || undefined}
        data-readonly={readOnly || undefined}
        data-error={Boolean(error) || undefined}
      >
        {leadingIcon && <span className={styles.inputAdornment} aria-hidden="true">{leadingIcon}</span>}
        <input
          ref={ref}
          id={inputId}
          className={cx(styles.input, className)}
          disabled={disabled}
          readOnly={readOnly}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...props}
        />
        {trailingAction && <span className={styles.inputAdornment}>{trailingAction}</span>}
      </div>
      {helperText && <FieldDescription id={helperId}>{helperText}</FieldDescription>}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  );
});
