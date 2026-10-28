import { ChevronDown } from "lucide-react";
import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { iconDefaults } from "@/lib/iconography";
import styles from "./primitives.module.css";
import { Field, FieldDescription, FieldError, FieldLabel } from "./field";
import { cx } from "./utils";
import type { ControlSize } from "./button";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?: ReactNode;
  placeholder?: string;
  helperText?: ReactNode;
  error?: ReactNode;
  options: SelectOption[];
  controlSize?: ControlSize;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    id,
    label,
    placeholder,
    helperText,
    error,
    options,
    controlSize = "md",
    className,
    disabled,
    multiple,
    "aria-describedby": ariaDescribedBy,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const helperId = helperText ? `${selectId}-description` : undefined;
  const errorId = error ? `${selectId}-error` : undefined;
  const describedBy = [ariaDescribedBy, helperId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <Field>
      {label && <FieldLabel htmlFor={selectId}>{label}</FieldLabel>}
      <div
        className={styles.selectShell}
        data-size={controlSize}
        data-multiple={multiple || undefined}
        data-disabled={disabled || undefined}
        data-error={Boolean(error) || undefined}
      >
        <select
          ref={ref}
          id={selectId}
          className={cx(styles.select, className)}
          disabled={disabled}
          multiple={multiple}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...props}
        >
          {placeholder && <option value="" disabled>{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>
          ))}
        </select>
        <span className={styles.selectAdornment} aria-hidden="true">
          <ChevronDown {...iconDefaults} />
        </span>
      </div>
      {helperText && <FieldDescription id={helperId}>{helperText}</FieldDescription>}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  );
});