"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import { IconButton, Tooltip } from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import styles from "./product-components.module.css";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export interface ResourceIdentifierProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
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

  return (
    <div className={classNames(styles.resourceIdentifier, className)} {...props}>
      <div className={styles.resourceValues}>
        <span className={styles.resourcePrimary}>{primary}</span>
        {technicalId && (
          <Tooltip content={technicalId}>
            <span className={styles.resourceTechnical} tabIndex={0}>{technicalId}</span>
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
