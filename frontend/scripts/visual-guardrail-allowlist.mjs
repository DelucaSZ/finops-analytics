export const VISUAL_GUARDRAIL_ALLOWLIST = Object.freeze([
  Object.freeze({
    path: "app/globals.css",
    reason: "Aven design-token and theme source. Raw visual values are definitions consumed through semantic tokens, not component-level styling.",
  }),
]);

export function isVisualGuardrailAllowlisted(filename) {
  const normalized = filename.replaceAll("\\", "/").replace(/^\.\//, "").replace(/^frontend\//, "");
  return VISUAL_GUARDRAIL_ALLOWLIST.some((entry) => entry.path === normalized);
}
