import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import styles from "./primitives.module.css";
import { Spinner } from "./spinner";
import { cx } from "./utils";

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";
export type ControlSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ControlSize;
  loading?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    leadingIcon,
    trailingIcon,
    className,
    disabled,
    children,
    type = "button",
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(styles.button, className)}
      data-variant={variant}
      data-size={size}
      data-loading={loading || undefined}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {(loading || leadingIcon) && (
        <span className={styles.buttonIcon} aria-hidden="true">
          {loading ? <Spinner size="sm" /> : leadingIcon}
        </span>
      )}
      <span>{children}</span>
      {!loading && trailingIcon && <span className={styles.buttonIcon} aria-hidden="true">{trailingIcon}</span>}
    </button>
  );
});
