"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import type { HTMLAttributes } from "react";
import { iconDefaults } from "@/lib/iconography";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export interface PaginationProps extends Omit<HTMLAttributes<HTMLElement>, "onChange"> {
  page: number;
  pageCount: number;
  onPageChange(page: number): void;
}

function pagesFor(page: number, pageCount: number) {
  const values = new Set([1, pageCount, page - 1, page, page + 1]);
  return [...values].filter((value) => value >= 1 && value <= pageCount).sort((a, b) => a - b);
}

export function Pagination({ page, pageCount, onPageChange, className, ...props }: PaginationProps) {
  const pages = pagesFor(page, pageCount);
  return (
    <nav className={cx(styles.pagination, className)} aria-label="Paginação" {...props}>
      <button className={styles.paginationButton} type="button" disabled={page <= 1} aria-label="Página anterior" onClick={() => onPageChange(page - 1)}>
        <ChevronLeft {...iconDefaults} />
      </button>
      {pages.map((value, index) => {
        const previous = pages[index - 1];
        return (
          <span key={value} className={styles.pagination}>
            {previous && value - previous > 1 && <span className={styles.paginationEllipsis} aria-hidden="true">…</span>}
            <button
              className={styles.paginationButton}
              type="button"
              aria-label={`Página ${value}`}
              aria-current={value === page ? "page" : undefined}
              onClick={() => onPageChange(value)}
            >
              {value}
            </button>
          </span>
        );
      })}
      <button className={styles.paginationButton} type="button" disabled={page >= pageCount} aria-label="Próxima página" onClick={() => onPageChange(page + 1)}>
        <ChevronRight {...iconDefaults} />
      </button>
    </nav>
  );
}
