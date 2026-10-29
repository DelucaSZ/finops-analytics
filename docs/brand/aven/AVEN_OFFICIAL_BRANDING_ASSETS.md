# Aven Official Branding Assets

Task 24.31 makes `frontend/public/brand/aven/` the runtime source for approved Aven Brand Kit v1 artwork.

## Runtime contract

`frontend/lib/brand.ts` owns stable asset paths. `frontend/components/brand/brand-logo.tsx` owns selection of approved artwork by logo variant and rendering surface. Product pages and shell/auth consumers must not select arbitrary logo files directly.

The production variants are:

- `horizontal` — approved horizontal lockup for compact brand placement;
- `vertical` — approved vertical lockup containing the official brand signature;
- `mark` — approved isolated Aven symbol;
- `surface="light" | "dark"` — selects artwork prepared for the actual rendering surface.

When a consumer knows its surface, it should pass `surface` explicitly. The component retains automatic surface resolution only as a compatibility path for surfaces whose light/dark role follows the resolved Theme Engine. A fixed dark surface must request `surface="dark"` even when the global application theme is Light.

## Official production assets

The PNG files under `frontend/public/brand/aven/` are downsampled, browser-appropriate derivatives of the approved Aven Brand Kit v1 masters. Downsampling preserves aspect ratio and artwork; no wordmark, symbol, color, composition or typography is reconstructed. The supplied `favicon.ico` and `apple-touch-icon.png` are copied from the kit unchanged.

The Brand Kit masters remain the visual source of truth. No production derivative is artificially upscaled or altered with AI.

## SVG fallback policy

`aven-logo-horizontal-fallback.svg` and `aven-icon-gradient.svg` remain in the repository only as technical vector fallbacks for compatibility or contexts that strictly require vector output. The horizontal SVG contains an approximate technical wordmark and must not be used as the primary Login or Application Shell representation.

Do not recreate the AVEN wordmark with HTML text, CSS `invert()`, `brightness()`, `mix-blend-mode`, opacity tricks, or other transformations intended to synthesize a missing surface variant.
