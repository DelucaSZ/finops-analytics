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
      {/* Repository wordmark fallback remains available for explicit institutional use only. */}
      <img className={styles.wordmark} src={brand.assets.wordmarkFallback} alt="" />
      {/* Official gradient symbol is the runtime-safe asset while approved raster masters are pending. */}
      <img className={styles.symbol} src={brand.assets.symbolGradient} alt="" />
    </span>
  );
}
