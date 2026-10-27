import { brand } from "@/lib/brand";
import styles from "./brand-logo.module.css";

export type BrandLogoVariant = "auto" | "wordmark" | "symbol";

export function BrandLogo({
  variant = "auto",
  decorative = false,
  className,
}: {
  variant?: BrandLogoVariant;
  decorative?: boolean;
  className?: string;
}) {
  const variantClass =
    variant === "symbol"
      ? styles.symbolOnly
      : variant === "wordmark"
        ? styles.wordmarkOnly
        : styles.auto;
  const classes = [styles.root, variantClass, className].filter(Boolean).join(" ");

  return (
    <span
      className={classes}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : brand.name}
      aria-hidden={decorative || undefined}
    >
      {/* Official repository wordmark fallback. Approved production PNG remains the visual master. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className={styles.wordmark} src={brand.assets.wordmarkFallback} alt="" />
      {/* Official gradient symbol is the safe dark/runtime fallback while raster masters are pending. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className={styles.symbol} src={brand.assets.symbolGradient} alt="" />
    </span>
  );
}
