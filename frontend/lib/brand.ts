export const PRODUCT_NAME = "Aven";
export const PRODUCT_TAGLINE = "Clarity. Flow. Control.";
export const PRODUCT_DESCRIPTION =
  "Plataforma FinOps Multi-Cloud para visibilidade, otimização, governança e controle de custos em cloud.";

export const brand = Object.freeze({
  name: PRODUCT_NAME,
  tagline: PRODUCT_TAGLINE,
  description: PRODUCT_DESCRIPTION,
  assets: Object.freeze({
    wordmarkFallback: "/brand/aven/aven-logo-horizontal-fallback.svg",
    symbolGradient: "/brand/aven/aven-icon-gradient.svg",
  }),
});

export function productTitle(section?: string): string {
  return section ? `${PRODUCT_NAME} — ${section}` : PRODUCT_NAME;
}
