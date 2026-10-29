"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import { IconButton, Tooltip } from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import styles from "./product-components.module.css";

const COMPACT_IDENTIFIER_THRESHOLD = 36;
const COMPACT_IDENTIFIER_PREFIX = 18;
const COMPACT_IDENTIFIER_SUFFIX = 8;

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export function compactResourceIdentifier(value: string) {
  const normalized = value.trim();
  if (normalized.length <= COMPACT_IDENTIFIER_THRESHOLD) return normalized;
  return `${normalized.slice(0, COMPACT_IDENTIFIER_PREFIX)}…${normalized.slice(-COMPACT_IDENTIFIER_SUFFIX)}`;
}

export interface ResourceIdentifierProps extends Omit<HTMLAttributes<HTMLDivElement>, "children" | "onCopy"> {
  primary: ReactNode;
  technicalId?: string | null;
  copyValue?: string;
  copyable?: boolean;
  copyLabel?: string;
  copiedLabel?: string;
  onCopy?: (value: string) => void;
}

export function ResourceIdentifier({
  primary,
  technicalId,
  copyValue,
  copyable = true,
  copyLabel = "Copy resource identifier",
  copiedLabel = "Copied",
  onCopy,
  className,
  ...props
}: ResourceIdentifierProps) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<number | null>(null);
  const valueToCopy = copyValue ?? technicalId ?? "";
  const primaryText = typeof primary === "string" ? primary.trim() : null;
  const compactPrimary = primaryText ? compactResourceIdentifier(primaryText) : primary;
  const primaryIsCompacted = Boolean(primaryText && compactPrimary !== primaryText);
  const compactTechnicalId = technicalId ? compactResourceIdentifier(technicalId) : null;

  useEffect(() => () => {
    if (timeoutRef.current != null) window.clearTimeout(timeoutRef.current);
  }, []);

  const handleCopy = async () => {
    if (!valueToCopy || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(valueToCopy);
      setCopied(true);
      onCopy?.(valueToCopy);
      if (timeoutRef.current != null) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const primaryNode = (
    <span className={styles.resourcePrimary} tabIndex={primaryIsCompacted ? 0 : undefined}>
      {compactPrimary}
    </span>
  );

  return (
    <div className={classNames(styles.resourceIdentifier, className)} {...props}>
      <div className={styles.resourceValues}>
        {primaryIsCompacted && primaryText ? <Tooltip content={primaryText}>{primaryNode}</Tooltip> : primaryNode}
        {technicalId && compactTechnicalId && (
          <Tooltip content={technicalId}>
            <span className={styles.resourceTechnical} tabIndex={0}>{compactTechnicalId}</span>
          </Tooltip>
        )}
      </div>
      {copyable && valueToCopy && (
        <IconButton
          aria-label={copied ? copiedLabel : copyLabel}
          tooltip={copied ? copiedLabel : copyLabel}
          size="sm"
          onClick={handleCopy}
        >
          {copied ? <Check {...iconDefaults} /> : <Copy {...iconDefaults} />}
        </IconButton>
      )}
    </div>
  );
}
