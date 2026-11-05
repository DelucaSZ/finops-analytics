# Aven Official Branding Assets

Task 24.31 makes `frontend/public/brand/aven/` the runtime source for approved Aven Brand Kit v1 artwork.

## Runtime contract

`frontend/lib/brand.ts` owns stable asset paths. `frontend/components/brand/brand-logo.tsx` owns selection of approved artwork by logo variant and rendering surface. Product pages and shell/auth consumers must not select arbitrary logo files directly.

The production variants are:

- `horizontal` — approved horizontal lockup;
- `horizontalNoTagline` — official horizontal lockup without signature;
- `vertical` — approved vertical lockup;
- `verticalNoTagline` — official vertical lockup without signature;
- `mark` — approved isolated Aven symbol;
- `surface="light" | "dark"` — selects artwork prepared for the actual rendering surface.

When a consumer knows its surface, it should pass `surface` explicitly. The component retains automatic surface resolution only as a compatibility path for surfaces whose light/dark role follows the resolved Theme Engine. A fixed dark surface must request `surface="dark"` even when the global application theme is Light.

## Official production assets

The current runtime asset map (`frontend/lib/brand.ts`) selects official 4096-resolution SVG lockups for light/dark surfaces. The product uses those mapped paths in Login, Shell and other branded surfaces; it must not substitute approximate text-rendered marks. The isolated vector icon, ambient SVG backgrounds, `favicon.ico` and `apple-touch-icon.png` are also exposed from the versioned runtime directory.

The original Brand Kit remains the artwork source of truth. Do not upscale low-resolution images, fabricate wordmarks or replace official surface variants with CSS filters.

## SVG fallback policy

`aven-logo-horizontal-fallback.svg` remains an approximate technical compatibility fallback and must not be used for primary Login or Application Shell branding. `aven-icon-gradient.svg` is the official isolated mark and may be used where an icon, rather than a wordmark, is required.

Do not recreate the AVEN wordmark with HTML text, CSS `invert()`, `brightness()`, `mix-blend-mode`, opacity tricks, or other transformations intended to synthesize a missing surface variant.
