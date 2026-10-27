"use client";

import { useMemo, useState, type ChangeEvent, type HTMLAttributes } from "react";
import { Button, Input, Select, Skeleton } from "@/components/ui";
import styles from "./product-components.module.css";
import type { AccountSelectorOption, ProductSelectorOption } from "./types";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

interface SelectorCommonProps<T extends ProductSelectorOption> extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  options: T[];
  label: string;
  placeholder?: string;
  searchable?: boolean;
  searchPlaceholder?: string;
  clearable?: boolean;
  disabled?: boolean;
  loading?: boolean;
  emptyLabel?: string;
  getOptionLabel?: (option: T) => string;
}

interface SingleSelectorProps {
  multiple?: false;
  value: string;
  onChange: (value: string) => void;
  selectAll?: never;
}

interface MultipleSelectorProps {
  multiple: true;
  value: string[];
  onChange: (value: string[]) => void;
  selectAll?: boolean;
}

type ProductSelectorProps<T extends ProductSelectorOption> = SelectorCommonProps<T> & (SingleSelectorProps | MultipleSelectorProps);

function ProductSelector<T extends ProductSelectorOption>({
  options,
  label,
  placeholder = "Select",
  searchable = false,
  searchPlaceholder = "Search",
  clearable = true,
  disabled = false,
  loading = false,
  emptyLabel = "No options available",
  getOptionLabel = (option) => option.label,
  className,
  ...selection
}: ProductSelectorProps<T>) {
  const [search, setSearch] = useState("");
  const filteredOptions = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    if (!query) return options;
    return options.filter((option) => {
      const searchableText = [
        option.label,
        option.description,
        ...(option.searchTerms ?? []),
      ].filter(Boolean).join(" ").toLocaleLowerCase();
      return searchableText.includes(query);
    });
  }, [options, search]);

  const selectOptions = filteredOptions.map((option) => ({
    value: option.value,
    label: getOptionLabel(option),
    disabled: option.disabled,
  }));

  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    if (selection.multiple) {
      selection.onChange(Array.from(event.currentTarget.selectedOptions, (option) => option.value));
      return;
    }
    selection.onChange(event.currentTarget.value);
  };

  const handleClear = () => {
    if (selection.multiple) selection.onChange([]);
    else selection.onChange("");
  };

  const handleSelectAll = () => {
    if (!selection.multiple) return;
    selection.onChange(options.filter((option) => !option.disabled).map((option) => option.value));
  };

  const hasSelection = selection.multiple ? selection.value.length > 0 : Boolean(selection.value);
  const hasOptions = selectOptions.length > 0;

  return (
    <div className={classNames(styles.selector, className)}>
      {searchable && (
        <Input
          aria-label={`${label} search`}
          placeholder={searchPlaceholder}
          value={search}
          disabled={disabled || loading}
          onChange={(event) => setSearch(event.target.value)}
          controlSize="sm"
        />
      )}
      {loading ? (
        <div className={styles.selectorLoading} role="status" aria-label={`Loading ${label}`}>
          <Skeleton />
        </div>
      ) : (
        <Select
          label={label}
          placeholder={hasOptions && !selection.multiple ? placeholder : undefined}
          options={hasOptions ? selectOptions : [{ value: "__empty__", label: emptyLabel, disabled: true }]}
          value={selection.value}
          multiple={selection.multiple}
          disabled={disabled || !hasOptions}
          onChange={handleChange}
          className={selection.multiple ? styles.multiSelect : undefined}
        />
      )}
      {(clearable || (selection.multiple && selection.selectAll)) && (
        <div className={styles.selectorActions}>
          {selection.multiple && selection.selectAll && (
            <Button variant="ghost" size="sm" disabled={disabled || loading || options.length === 0} onClick={handleSelectAll}>
              Select all
            </Button>
          )}
          {clearable && (
            <Button variant="ghost" size="sm" disabled={disabled || loading || !hasSelection} onClick={handleClear}>
              Clear
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export type AccountSelectorProps = SelectorCommonProps<AccountSelectorOption> & (SingleSelectorProps | MultipleSelectorProps);

export function AccountSelector(props: AccountSelectorProps) {
  return (
    <ProductSelector
      {...props}
      searchable={props.searchable ?? true}
      getOptionLabel={(account) => {
        const metadata = [account.accountId, account.provider, account.environment].filter(Boolean);
        return metadata.length ? `${account.label} · ${metadata.join(" · ")}` : account.label;
      }}
    />
  );
}

export type EnvironmentSelectorProps = SelectorCommonProps<ProductSelectorOption> & (SingleSelectorProps | MultipleSelectorProps);

export function EnvironmentSelector(props: EnvironmentSelectorProps) {
  return <ProductSelector {...props} />;
}

export type ProviderSelectorProps = SelectorCommonProps<ProductSelectorOption> & (SingleSelectorProps | MultipleSelectorProps);

export function ProviderSelector(props: ProviderSelectorProps) {
  return <ProductSelector {...props} />;
}
