export interface OverlayPosition {
  top: number;
  left: number;
}

export interface DropdownPosition extends OverlayPosition {
  maxBlockSize: number;
  side: "top" | "bottom";
}

function readViewportInset() {
  const raw = window.getComputedStyle(document.documentElement).getPropertyValue("--space-2").trim();
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) ? value : 0;
}

function clampInlinePosition(preferredLeft: number, overlayWidth: number, inset: number) {
  const maxLeft = Math.max(inset, window.innerWidth - overlayWidth - inset);
  return Math.min(Math.max(preferredLeft, inset), maxLeft);
}

export function positionDropdown(trigger: DOMRect, overlay: DOMRect): DropdownPosition {
  const inset = readViewportInset();
  const availableBelow = Math.max(0, window.innerHeight - trigger.bottom - inset);
  const availableAbove = Math.max(0, trigger.top - inset);
  const side = overlay.height > availableBelow && availableAbove > availableBelow ? "top" : "bottom";
  const maxBlockSize = side === "top" ? availableAbove : availableBelow;
  const visibleHeight = Math.min(overlay.height, maxBlockSize);
  const top = side === "top"
    ? Math.max(inset, trigger.top - inset - visibleHeight)
    : Math.min(trigger.bottom + inset, Math.max(inset, window.innerHeight - visibleHeight - inset));

  return {
    top,
    left: clampInlinePosition(trigger.left, overlay.width, inset),
    maxBlockSize,
    side,
  };
}

export function positionTooltip(trigger: DOMRect, overlay: DOMRect): OverlayPosition {
  const inset = readViewportInset();
  const availableAbove = Math.max(0, trigger.top - inset);
  const availableBelow = Math.max(0, window.innerHeight - trigger.bottom - inset);
  const placeAbove = overlay.height <= availableAbove || availableAbove >= availableBelow;
  const preferredTop = placeAbove
    ? trigger.top - inset - overlay.height
    : trigger.bottom + inset;
  const maxTop = Math.max(inset, window.innerHeight - overlay.height - inset);

  return {
    top: Math.min(Math.max(preferredTop, inset), maxTop),
    left: clampInlinePosition(trigger.left + trigger.width / 2 - overlay.width / 2, overlay.width, inset),
  };
}
