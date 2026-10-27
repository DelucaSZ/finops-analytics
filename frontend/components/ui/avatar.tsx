"use client";

import { useState, type HTMLAttributes } from "react";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> {
  src?: string;
  alt?: string;
  fallback: string;
  size?: "sm" | "md" | "lg";
}

export function Avatar({ src, alt = "", fallback, size = "md", className, ...props }: AvatarProps) {
  const [failed, setFailed] = useState(false);
  return (
    <span className={cx(styles.avatar, className)} data-size={size} {...props}>
      {src && !failed ? (
        // Avatar accepts runtime image URLs; next/image would require domain configuration per consumer.
        // eslint-disable-next-line @next/next/no-img-element
        <img className={styles.avatarImage} src={src} alt={alt} onError={() => setFailed(true)} />
      ) : (
        <span aria-label={alt || fallback}>{fallback}</span>
      )}
    </span>
  );
}
