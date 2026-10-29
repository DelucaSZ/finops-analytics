import type {
  HTMLAttributes,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export function Table({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <div className={styles.tableWrapper} data-aven-table><table className={cx(styles.table, className)} {...props} /></div>;
}

export function TableHeader(props: HTMLAttributes<HTMLTableSectionElement>) { return <thead {...props} />; }
export function TableBody(props: HTMLAttributes<HTMLTableSectionElement>) { return <tbody {...props} />; }
export function TableFooter(props: HTMLAttributes<HTMLTableSectionElement>) { return <tfoot {...props} />; }
export function TableCaption(props: HTMLAttributes<HTMLTableCaptionElement>) { return <caption {...props} />; }

export interface TableRowProps extends HTMLAttributes<HTMLTableRowElement> {
  selected?: boolean;
  staticRow?: boolean;
}

export function TableRow({ selected, staticRow, className, ...props }: TableRowProps) {
  return <tr className={cx(styles.tableRow, className)} data-selected={selected || undefined} data-static={staticRow || undefined} {...props} />;
}

export interface TableHeadProps extends ThHTMLAttributes<HTMLTableCellElement> { numeric?: boolean; }
export function TableHead({ numeric, className, ...props }: TableHeadProps) {
  return <th className={cx(styles.tableHead, className)} data-numeric={numeric || undefined} scope={props.scope ?? "col"} {...props} />;
}

export interface TableCellProps extends TdHTMLAttributes<HTMLTableCellElement> { numeric?: boolean; }
export function TableCell({ numeric, className, ...props }: TableCellProps) {
  return <td className={cx(styles.tableCell, className)} data-numeric={numeric || undefined} {...props} />;
}

export interface TableStateProps extends TdHTMLAttributes<HTMLTableCellElement> {
  state: "loading" | "empty";
}

export function TableState({ state, className, children, ...props }: TableStateProps) {
  return <td className={cx(styles.tableState, className)} data-state={state} {...props}>{children}</td>;
}
