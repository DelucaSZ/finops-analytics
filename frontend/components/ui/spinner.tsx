import { LoaderCircle } from "lucide-react";
import type { HTMLAttributes } from "react";
import { iconStrokeWidths } from "@/lib/iconography";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export interface SpinnerProps extends HTMLAttributes<HTMLSpanElement> {
  size?: "sm" | "md" | "lg";
  label?: string;
}

export function Spinner({ size = "md", label, className, ...props }: SpinnerProps) {
  return (
    <span
      className={cx(styles.spinner, className)}
      data-size={size}
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      {...props}
    >
      <LoaderCircle size="100%" strokeWidth={iconStrokeWidths.default} />
    </span>
  );
}
