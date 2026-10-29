"use client";

import Image from "next/image";
import { useTheme } from "@/components/theme-provider";
import { brand } from "@/lib/brand";
import styles from "./brand-logo.module.css";

export type AvenLogoVariant = "horizontal" | "vertical" | "mark";
export type AvenLogoSurface = "light" | "dark";
export type BrandLogoVariant = AvenLogoVariant | "wordmark" | "symbol";

interface AvenLogoProps {
  variant?: BrandLogoVariant;
  surface?: AvenLogoSurface;
  decorative?: boolean;
  priority?: boolean;
  className?: string;
}

const dimensions = {
  horizontal: { width: 240, height: 94 },
  vertical: { width: 160, height: 160 },
  mark: { width: 96, height: 96 },
} as const;

function normalizeVariant(variant: BrandLogoVariant): AvenLogoVariant {
  if (variant === "wordmark") return "horizontal";
  if (variant === "symbol") return "mark";
  return variant;
}

function logoSource(variant: AvenLogoVariant, surface: AvenLogoSurface) {
  const surfaceKey = surface === "dark" ? "onDark" : "onLight";
  if (variant === "mark") return brand.assets.mark.gradient;
  return brand.assets.logo[variant][surfaceKey];
}

export function AvenLogo({
  variant = "horizontal",
  surface,
  decorative = false,
  priority = false,
  className,
}: AvenLogoProps) {
  const { resolvedTheme } = useTheme();
  const resolvedSurface: AvenLogoSurface = surface ?? (resolvedTheme === "dark" ? "dark" : "light");
  const resolvedVariant = normalizeVariant(variant);
  const source = logoSource(resolvedVariant, resolvedSurface);
  const size = dimensions[resolvedVariant];
  const classes = [styles.root, styles[resolvedVariant], className].filter(Boolean).join(" ");

  return (
    <span className={classes} data-aven-logo={resolvedVariant} data-surface={resolvedSurface}>
      <Image
        className={styles.image}
        src={source}
        alt={decorative ? "" : brand.name}
        width={size.width}
        height={size.height}
        priority={priority}
      />
    </span>
  );
}

// Compatibility references document the retained technical SVG fallbacks without rendering them.
export const AVEN_VECTOR_WORDMARK_FALLBACK = brand.assets.wordmarkFallback;
export const AVEN_VECTOR_SYMBOL_FALLBACK = brand.assets.symbolGradient;

// Compatibility export for pre-24.31 consumers. New code should prefer AvenLogo.
export const BrandLogo = AvenLogo;
