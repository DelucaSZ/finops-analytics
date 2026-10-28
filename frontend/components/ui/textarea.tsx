import { forwardRef, useId, type ReactNode, type TextareaHTMLAttributes } from "react";
import styles from "./primitives.module.css";
import { Field, FieldDescription, FieldError, FieldLabel } from "./field";
import { cx } from "./utils";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  resize?: "none" | "vertical" | "both";
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  {
    id,
    label,
    helperText,
    error,
    resize = "vertical",
    className,
    disabled,
    readOnly,
    "aria-describedby": ariaDescribedBy,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const textareaId = id ?? generatedId;
  const helperId = helperText ? `${textareaId}-description` : undefined;
  const errorId = error ? `${textareaId}-error` : undefined;
  const describedBy = [ariaDescribedBy, helperId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <Field>
      {label && <FieldLabel htmlFor={textareaId}>{label}</FieldLabel>}
      <div
        className={styles.textareaShell}
        data-disabled={disabled || undefined}
        data-readonly={readOnly || undefined}
        data-error={Boolean(error) || undefined}
      >
        <textarea
          ref={ref}
          id={textareaId}
          className={cx(styles.textarea, className)}
          data-aven-control-inner=""
          data-resize={resize}
          disabled={disabled}
          readOnly={readOnly}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...props}
        />
      </div>
      {helperText && <FieldDescription id={helperId}>{helperText}</FieldDescription>}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  );
});
