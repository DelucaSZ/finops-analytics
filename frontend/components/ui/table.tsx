import type {
  HTMLAttributes,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import styles from "./table.module.css";
import { cx } from "./utils";

export type TableDensity = "compact" | "default" | "comfortable";
export type TableColumnKind =
  | "selection"
  | "identifier"
  | "text"
  | "provider"
  | "badge"
  | "status"
  | "numeric"
  | "currency"
  | "date"
  | "actions";

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  density?: TableDensity;
}

export function Table({ density = "default", className, ...props }: TableProps) {
  return (
    <div className={styles.tableWrapper} data-aven-table data-density={density}>
      <table
        className={cx(styles.table, className)}
        data-density={density}
        {...props}
      />
    </div>
  );
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

export interface TableHeadProps extends ThHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
  kind?: TableColumnKind;
}

export function TableHead({ numeric, kind, className, ...props }: TableHeadProps) {
  const numericColumn = numeric || kind === "numeric" || kind === "currency";
  return (
    <th
      className={cx(styles.tableHead, className)}
      data-column-kind={kind}
      data-numeric={numericColumn || undefined}
      scope={props.scope ?? "col"}
      {...props}
    />
  );
}

export interface TableCellProps extends TdHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
  kind?: TableColumnKind;
}

export function TableCell({ numeric, kind, className, ...props }: TableCellProps) {
  const numericColumn = numeric || kind === "numeric" || kind === "currency";
  return (
    <td
      className={cx(styles.tableCell, className)}
      data-column-kind={kind}
      data-numeric={numericColumn || undefined}
      {...props}
    />
  );
}

export interface TableStateProps extends TdHTMLAttributes<HTMLTableCellElement> {
  state: "loading" | "empty";
}

export function TableState({ state, className, children, ...props }: TableStateProps) {
  return <td className={cx(styles.tableState, className)} data-state={state} {...props}>{children}</td>;
}
