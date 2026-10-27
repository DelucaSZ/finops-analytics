import { forwardRef, type FieldsetHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import styles from "./primitives.module.css";
import { cx } from "./utils";

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: ReactNode;
  description?: ReactNode;
}

export const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { label, description, className, disabled, ...props },
  ref,
) {
  return (
    <label className={cx(styles.choiceLabel, className)}>
      <input ref={ref} type="radio" className={styles.choiceInput} disabled={disabled} {...props} />
      <span className={styles.radioMark} aria-hidden="true"><span className={styles.choiceIcon} /></span>
      {(label || description) && (
        <span className={styles.choiceText}>
          {label && <span>{label}</span>}
          {description && <span className={styles.choiceDescription}>{description}</span>}
        </span>
      )}
    </label>
  );
});

export interface RadioGroupProps extends FieldsetHTMLAttributes<HTMLFieldSetElement> {
  legend?: ReactNode;
}

export function RadioGroup({ legend, className, children, ...props }: RadioGroupProps) {
  return (
    <fieldset className={cx(styles.radioGroup, className)} {...props}>
      {legend && <legend className={styles.radioLegend}>{legend}</legend>}
      {children}
    </fieldset>
  );
}
