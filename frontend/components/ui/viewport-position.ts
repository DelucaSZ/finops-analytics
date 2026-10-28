export interface OverlayPosition {
  top: number;
  left: number;
}

export interface DropdownPosition extends OverlayPosition {
  maxBlockSize: number;
  minInlineSize: number;
  side: "top" | "bottom";
}

interface ViewportBounds {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

function readViewportInset() {
  const raw = window.getComputedStyle(document.documentElement).getPropertyValue("--space-2").trim();
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) ? value : 0;
}

function readViewportBounds(): ViewportBounds {
  const viewport = window.visualViewport;
  const left = viewport?.offsetLeft ?? 0;
  const top = viewport?.offsetTop ?? 0;
  const width = viewport?.width ?? window.innerWidth;
  const height = viewport?.height ?? window.innerHeight;
  return { top, right: left + width, bottom: top + height, left };
}

function clampInlinePosition(preferredLeft: number, overlayWidth: number, inset: number, viewport: ViewportBounds) {
  const minLeft = viewport.left + inset;
  const maxLeft = Math.max(minLeft, viewport.right - overlayWidth - inset);
  return Math.min(Math.max(preferredLeft, minLeft), maxLeft);
}

export function positionDropdown(trigger: DOMRect, overlay: DOMRect): DropdownPosition {
  const inset = readViewportInset();
  const viewport = readViewportBounds();
  const minTop = viewport.top + inset;
  const maxBottom = viewport.bottom - inset;
  const availableBelow = Math.max(0, maxBottom - trigger.bottom - inset);
  const availableAbove = Math.max(0, trigger.top - minTop - inset);
  const side = overlay.height > availableBelow && availableAbove > availableBelow ? "top" : "bottom";
  const maxBlockSize = side === "top" ? availableAbove : availableBelow;
  const visibleHeight = Math.min(overlay.height, maxBlockSize);
  const top = side === "top"
    ? Math.max(minTop, trigger.top - inset - visibleHeight)
    : Math.min(trigger.bottom + inset, Math.max(minTop, maxBottom - visibleHeight));

  return {
    top,
    left: clampInlinePosition(trigger.left, overlay.width, inset, viewport),
    maxBlockSize,
    minInlineSize: trigger.width,
    side,
  };
}

export function positionTooltip(trigger: DOMRect, overlay: DOMRect): OverlayPosition {
  const inset = readViewportInset();
  const viewport = readViewportBounds();
  const minTop = viewport.top + inset;
  const maxBottom = viewport.bottom - inset;
  const availableAbove = Math.max(0, trigger.top - minTop - inset);
  const availableBelow = Math.max(0, maxBottom - trigger.bottom - inset);
  const placeAbove = overlay.height <= availableAbove || availableAbove >= availableBelow;
  const preferredTop = placeAbove
    ? trigger.top - inset - overlay.height
    : trigger.bottom + inset;
  const maxTop = Math.max(minTop, maxBottom - overlay.height);

  return {
    top: Math.min(Math.max(preferredTop, minTop), maxTop),
    left: clampInlinePosition(trigger.left + trigger.width / 2 - overlay.width / 2, overlay.width, inset, viewport),
  };
}
