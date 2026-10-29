export const PRODUCT_NAME = "Aven";
export const PRODUCT_TAGLINE = "Clarity. Flow. Control.";
export const PRODUCT_DESCRIPTION =
  "Plataforma FinOps Multi-Cloud para visibilidade, otimização, governança e controle de custos em cloud.";

export const brand = Object.freeze({
  name: PRODUCT_NAME,
  tagline: PRODUCT_TAGLINE,
  description: PRODUCT_DESCRIPTION,
  assets: Object.freeze({
    logo: Object.freeze({
      horizontal: Object.freeze({
        onLight: "/brand/aven/aven-logo-horizontal-on-light.png",
        onDark: "/brand/aven/aven-logo-horizontal-on-dark.png",
      }),
      vertical: Object.freeze({
        onLight: "/brand/aven/aven-logo-vertical-on-light.png",
        onDark: "/brand/aven/aven-logo-vertical-on-dark.png",
      }),
    }),
    mark: Object.freeze({
      gradient: "/brand/aven/aven-mark-gradient.png",
    }),
    icons: Object.freeze({
      favicon: "/brand/aven/favicon.ico",
      appleTouch: "/brand/aven/apple-touch-icon.png",
    }),
    // Technical-only vector fallbacks. Never use these as the primary Login/Shell branding.
    wordmarkFallback: "/brand/aven/aven-logo-horizontal-fallback.svg",
    symbolGradient: "/brand/aven/aven-icon-gradient.svg",
  }),
});

export function productTitle(section?: string): string {
  return section ? `${PRODUCT_NAME} — ${section}` : PRODUCT_NAME;
}
