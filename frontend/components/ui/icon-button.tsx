import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import styles from "./primitives.module.css";
import { Spinner } from "./spinner";
import { Tooltip } from "./tooltip";
import { cx } from "./utils";
import type { ControlSize } from "./button";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  "aria-label": string;
  size?: ControlSize;
  loading?: boolean;
  tooltip?: string;
  children: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { size = "md", loading = false, tooltip, className, disabled, children, type = "button", ...props },
  ref,
) {
  const button = (
    <button
      ref={ref}
      type={type}
      className={cx(styles.iconButton, className)}
      data-size={size}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner size="sm" /> : children}
    </button>
  );

  return tooltip ? <Tooltip content={tooltip}>{button}</Tooltip> : button;
});
