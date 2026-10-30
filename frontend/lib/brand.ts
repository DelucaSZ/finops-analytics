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
        onLight: "/brand/aven/aven_logo_horizontal_light_ui_4096.svg",
        onDark: "/brand/aven/aven_logo_horizontal_dark_ui_4096.svg",
      }),
      horizontalNoTagline: Object.freeze({
        onLight: "/brand/aven/aven_logo_horizontal_no_tagline_light_ui_4096.svg",
        onDark: "/brand/aven/aven_logo_horizontal_no_tagline_dark_ui_4096.svg",
      }),
      vertical: Object.freeze({
        onLight: "/brand/aven/aven_logo_vertical_light_ui_4096.svg",
        onDark: "/brand/aven/aven_logo_vertical_dark_ui_4096.svg",
      }),
      verticalNoTagline: Object.freeze({
        onLight: "/brand/aven/aven_logo_vertical_no_tagline_dark_text_4096.svg",
        onDark: "/brand/aven/aven_logo_vertical_no_tagline_white_text_4096.svg",
      }),
    }),
    mark: Object.freeze({
      gradient: "/brand/aven/aven-icon-gradient.svg",
    }),
    icons: Object.freeze({
      favicon: "/brand/aven/favicon.ico",
      appleTouch: "/brand/aven/apple-touch-icon.png",
    }),
    // Technical-only compatibility aliases. Runtime Login/Shell branding uses the Full HD kit lockups above.
    wordmarkFallback: "/brand/aven/aven-logo-horizontal-fallback.svg",
    symbolGradient: "/brand/aven/aven-icon-gradient.svg",
  }),
});

export function productTitle(section?: string): string {
  return section ? `${PRODUCT_NAME} — ${section}` : PRODUCT_NAME;
}
