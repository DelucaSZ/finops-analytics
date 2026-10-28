"use client";

import {
  cloneElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import styles from "./overlays.module.css";
import { cx } from "./utils";
import { positionTooltip, type OverlayPosition } from "./viewport-position";

interface TooltipChildProps {
  "aria-describedby"?: string;
}

export interface TooltipProps extends Omit<HTMLAttributes<HTMLSpanElement>, "content" | "children"> {
  content: ReactNode;
  children: ReactElement<TooltipChildProps>;
}

export function Tooltip({ content, children, className, ...props }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [position, setPosition] = useState<OverlayPosition | null>(null);
  const rootRef = useRef<HTMLSpanElement | null>(null);
  const contentRef = useRef<HTMLSpanElement | null>(null);
  const contentId = useId();
  const describedBy = [children.props["aria-describedby"], open ? contentId : undefined].filter(Boolean).join(" ") || undefined;

  useEffect(() => setMounted(true), []);

  useLayoutEffect(() => {
    if (!open || !mounted) return;
    const updatePosition = () => {
      const trigger = rootRef.current;
      const tooltip = contentRef.current;
      if (trigger && tooltip) setPosition(positionTooltip(trigger.getBoundingClientRect(), tooltip.getBoundingClientRect()));
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [content, mounted, open]);

  return (
    <span
      ref={rootRef}
      className={cx(styles.tooltipRoot, className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
      {...props}
    >
      {cloneElement(children, { "aria-describedby": describedBy })}
      {mounted && createPortal(
        <span
          ref={contentRef}
          id={contentId}
          className={styles.tooltipContent}
          role="tooltip"
          data-state={open && position ? "open" : "closed"}
          style={position ? { top: position.top, left: position.left } : undefined}
        >
          {content}
        </span>,
        document.body,
      )}
    </span>
  );
}
