"use client";

import { ChevronDown } from "lucide-react";
import {
  useId,
  useMemo,
  useState,
  type ChangeEvent,
  type HTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  Button,
  Checkbox,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  Field,
  FieldLabel,
  Input,
  Select,
  Skeleton,
} from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
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
  clearLabel?: string;
  selectAllLabel?: string;
  disabled?: boolean;
  loading?: boolean;
  emptyLabel?: string;
  getOptionLabel?: (option: T) => string;
  getOptionDescription?: (option: T) => ReactNode;
  formatSelectionSummary?: (selectedOptions: T[], allSelected: boolean) => string;
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
  clearLabel = "Clear",
  selectAllLabel = "Select all",
  disabled = false,
  loading = false,
  emptyLabel = "No options available",
  getOptionLabel = (option) => option.label,
  getOptionDescription = (option) => option.description,
  formatSelectionSummary,
  className,
  ...selection
}: ProductSelectorProps<T>) {
  const triggerId = useId();
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

  const handleSingleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    if (!selection.multiple) selection.onChange(event.currentTarget.value);
  };

  const handleClear = () => {
    if (selection.multiple) {
      selection.onChange([]);
      return;
    }
    (selection as SingleSelectorProps).onChange("");
  };

  const selectedOptions = selection.multiple
    ? options.filter((option) => selection.value.includes(option.value))
    : [];
  const selectableOptions = options.filter((option) => !option.disabled);
  const selectedSelectableCount = selection.multiple
    ? selectableOptions.filter((option) => selection.value.includes(option.value)).length
    : 0;
  const allSelected = Boolean(
    selection.multiple
      && selectableOptions.length > 0
      && selectedSelectableCount === selectableOptions.length,
  );
  const partiallySelected = Boolean(selection.multiple && selectedSelectableCount > 0 && !allSelected);
  const hasSelection = selection.multiple ? selection.value.length > 0 : Boolean(selection.value);
  const hasOptions = selectOptions.length > 0;
  const selectionSummary = selection.multiple
    ? formatSelectionSummary?.(selectedOptions, allSelected)
      ?? (selection.value.length > 0 ? `${selection.value.length} selected` : placeholder)
    : "";

  const handleSelectAll = (checked: boolean) => {
    if (!selection.multiple) return;
    if (!checked) {
      selection.onChange([]);
      return;
    }
    selection.onChange(selectableOptions.map((option) => option.value));
  };

  const handleOptionChange = (option: T, checked: boolean) => {
    if (!selection.multiple) return;
    if (checked) {
      selection.onChange(Array.from(new Set([...selection.value, option.value])));
      return;
    }
    selection.onChange(selection.value.filter((value) => value !== option.value));
  };

  const preserveSearchCursorKeys = (event: KeyboardEvent<HTMLInputElement>) => {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) event.stopPropagation();
  };

  return (
    <div className={classNames(styles.selector, className)}>
      {loading ? (
        <div className={styles.selectorLoading} role="status" aria-label={`Loading ${label}`}>
          <Skeleton />
        </div>
      ) : selection.multiple ? (
        <DropdownMenu className={styles.selectorDropdownRoot}>
          <Field className={styles.selectorField}>
            <FieldLabel htmlFor={triggerId}>{label}</FieldLabel>
            <DropdownMenuTrigger
              id={triggerId}
              className={styles.selectorTrigger}
              disabled={disabled || options.length === 0}
              aria-label={`${label}: ${selectionSummary}`}
            >
              <span className={styles.selectorTriggerText}>{selectionSummary}</span>
              <ChevronDown className={styles.selectorChevron} {...iconDefaults} aria-hidden="true" />
            </DropdownMenuTrigger>
          </Field>
          <DropdownMenuContent className={styles.selectorDropdown} aria-label={label}>
            {searchable && (
              <div className={styles.selectorDropdownHeader}>
                <Input
                  autoFocus
                  aria-label={`${label} search`}
                  placeholder={searchPlaceholder}
                  value={search}
                  disabled={disabled}
                  onChange={(event) => setSearch(event.target.value)}
                  onKeyDown={preserveSearchCursorKeys}
                  controlSize="sm"
                />
              </div>
            )}
            {selection.selectAll && selectableOptions.length > 0 && (
              <div className={styles.selectorSelectAll}>
                <Checkbox
                  checked={allSelected}
                  indeterminate={partiallySelected}
                  onChange={(event) => handleSelectAll(event.target.checked)}
                  label={selectAllLabel}
                />
              </div>
            )}
            <div className={styles.selectorOptionList} role="group" aria-label={`${label} options`}>
              {filteredOptions.length > 0 ? (
                filteredOptions.map((option) => {
                  const description = getOptionDescription(option);
                  return (
                    <Checkbox
                      key={option.value}
                      className={styles.selectorOption}
                      checked={selection.value.includes(option.value)}
                      disabled={option.disabled}
                      onChange={(event) => handleOptionChange(option, event.target.checked)}
                      label={(
                        <span className={styles.selectorOptionCopy}>
                          <span className={styles.selectorOptionLabel}>{getOptionLabel(option)}</span>
                          {description && <span className={styles.selectorOptionDescription}>{description}</span>}
                        </span>
                      )}
                    />
                  );
                })
              ) : (
                <div className={styles.selectorEmpty} role="status">{emptyLabel}</div>
              )}
            </div>
            <div className={styles.selectorDropdownFooter}>
              <span className={styles.selectorSelectionCount}>{selectionSummary}</span>
              {clearable && (
                <Button variant="ghost" size="sm" disabled={disabled || !hasSelection} onClick={handleClear}>
                  {clearLabel}
                </Button>
              )}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <>
          {searchable && (
            <Input
              aria-label={`${label} search`}
              placeholder={searchPlaceholder}
              value={search}
              disabled={disabled}
              onChange={(event) => setSearch(event.target.value)}
              controlSize="sm"
            />
          )}
          <Select
            label={label}
            placeholder={hasOptions ? placeholder : undefined}
            options={hasOptions ? selectOptions : [{ value: "__empty__", label: emptyLabel, disabled: true }]}
            value={selection.value}
            disabled={disabled || !hasOptions}
            onChange={handleSingleChange}
          />
          {clearable && (
            <div className={styles.selectorActions}>
              <Button variant="ghost" size="sm" disabled={disabled || !hasSelection} onClick={handleClear}>
                {clearLabel}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export type AccountSelectorProps = SelectorCommonProps<AccountSelectorOption> & (SingleSelectorProps | MultipleSelectorProps);

export function AccountSelector(props: AccountSelectorProps) {
  return (
    <ProductSelector
      {...props}
      placeholder={props.placeholder ?? "Nenhuma conta selecionada"}
      searchable={props.searchable ?? true}
      getOptionLabel={(account) => {
        const metadata = [account.accountId, account.environment, account.provider?.toUpperCase()].filter(Boolean);
        if (props.multiple || metadata.length === 0) return account.label;
        return `${account.label} · ${metadata.join(" · ")}`;
      }}
      getOptionDescription={(account) => {
        if (!props.multiple) return undefined;
        const metadata = [account.accountId, account.environment, account.provider?.toUpperCase()].filter(Boolean);
        return metadata.length ? metadata.join(" · ") : undefined;
      }}
      formatSelectionSummary={(selectedOptions, allSelected) => {
        if (allSelected) return "Todas as contas selecionadas";
        if (selectedOptions.length === 0) return "Nenhuma conta selecionada";
        if (selectedOptions.length === 1) return "1 conta selecionada";
        return `${selectedOptions.length} contas selecionadas`;
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
