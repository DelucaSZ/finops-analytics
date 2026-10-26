import type { LucideProps } from "lucide-react";

/**
 * Canonical Aven icon geometry for lucide-react.
 *
 * Size/stroke values are CSS-variable references so CSS remains the visual
 * source of truth. Functional icons should inherit currentColor; semantic
 * color belongs to the consuming component, not to this module.
 */
export const iconSizes = Object.freeze({
  xs: "var(--icon-size-xs)",
  sm: "var(--icon-size-sm)",
  md: "var(--icon-size-md)",
  lg: "var(--icon-size-lg)",
  xl: "var(--icon-size-xl)",
  "2xl": "var(--icon-size-2xl)",
  "3xl": "var(--icon-size-3xl)",
} as const);

export const iconStrokeWidths = Object.freeze({
  default: "var(--icon-stroke-default)",
  strong: "var(--icon-stroke-strong)",
} as const);

export const iconHitTargets = Object.freeze({
  minimum: "var(--hit-target-min)",
  touch: "var(--hit-target-touch)",
} as const);

export const iconDefaults = {
  size: iconSizes.md,
  strokeWidth: iconStrokeWidths.default,
} satisfies Pick<LucideProps, "size" | "strokeWidth">;

export type AvenIconSize = keyof typeof iconSizes;
export type AvenIconStroke = keyof typeof iconStrokeWidths;
