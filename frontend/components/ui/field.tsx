import type { HTMLAttributes, LabelHTMLAttributes, ReactNode } from "react";
import styles from "./primitives.module.css";
import { cx } from "./utils";

export function Field({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx(styles.field, className)} {...props} />;
}

export function FieldLabel({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cx(styles.fieldLabel, className)} {...props} />;
}

export function FieldDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cx(styles.fieldDescription, className)} {...props} />;
}

export function FieldError({ className, children, ...props }: HTMLAttributes<HTMLParagraphElement> & { children: ReactNode }) {
  return <p className={cx(styles.fieldError, className)} role="alert" {...props}>{children}</p>;
}
