import type { HTMLAttributes } from "react";
import { cx } from "./utils";

export type SurfaceVariant = "section" | "panel" | "card" | "elevated" | "interactive";
export type SurfaceElement = "div" | "section" | "article";

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: SurfaceElement;
  variant?: SurfaceVariant;
}

export function Surface({
  as: Component = "div",
  variant = "section",
  className,
  ...props
}: SurfaceProps) {
  return (
    <Component
      className={cx(className)}
      data-aven-surface={variant}
      {...props}
    />
  );
}
