"use client";

import { useState, type HTMLAttributes } from "react";
import { Button, Input, Select } from "@/components/ui";
import styles from "./product-components.module.css";
import type { DateRangePreset, DateRangeValue } from "./types";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

function earlierDate(left?: string | null, right?: string | null) {
  if (!left) return right ?? undefined;
  if (!right) return left;
  return left < right ? left : right;
}

function laterDate(left?: string | null, right?: string | null) {
  if (!left) return right ?? undefined;
  if (!right) return left;
  return left > right ? left : right;
}

export interface DateRangePickerProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
  presets?: DateRangePreset[];
  presetValue?: string;
  onPresetChange?: (presetValue: string) => void;
  startLabel?: string;
  endLabel?: string;
  presetLabel?: string;
  presetPlaceholder?: string;
  clearLabel?: string;
  minDate?: string;
  maxDate?: string;
  disabled?: boolean;
  clearable?: boolean;
  showDateFields?: boolean;
}

export function DateRangePicker({
  value,
  onChange,
  presets = [],
  presetValue,
  onPresetChange,
  startLabel = "Start date",
  endLabel = "End date",
  presetLabel = "Period",
  presetPlaceholder = "Choose a period",
  clearLabel = "Clear dates",
  minDate,
  maxDate,
  disabled = false,
  clearable = true,
  showDateFields,
  className,
  ...props
}: DateRangePickerProps) {
  const [internalPreset, setInternalPreset] = useState("");
  const activePreset = presetValue ?? internalPreset;
  const activePresetDefinition = presets.find((preset) => preset.value === activePreset);
  const dateFieldsVisible = showDateFields
    ?? (presets.length === 0 || !activePreset || activePreset === "custom" || Boolean(activePresetDefinition?.range));

  const setPreset = (nextPreset: string) => {
    if (presetValue == null) setInternalPreset(nextPreset);
    onPresetChange?.(nextPreset);
    const preset = presets.find((item) => item.value === nextPreset);
    if (preset?.range) onChange(preset.range);
  };

  const clear = () => {
    if (presetValue == null) setInternalPreset("");
    onPresetChange?.("");
    onChange({ startDate: null, endDate: null });
  };

  return (
    <div
      className={classNames(styles.dateRangePicker, className)}
      data-date-fields={dateFieldsVisible ? "visible" : "hidden"}
      {...props}
    >
      {presets.length > 0 && (
        <Select
          label={presetLabel}
          placeholder={presetPlaceholder}
          options={presets.map((preset) => ({ value: preset.value, label: preset.label }))}
          value={activePreset}
          disabled={disabled}
          onChange={(event) => setPreset(event.target.value)}
          controlSize="sm"
        />
      )}
      {dateFieldsVisible && (
        <div className={styles.dateRangeFields}>
          <Input
            type="date"
            label={startLabel}
            value={value.startDate ?? ""}
            min={minDate}
            max={earlierDate(value.endDate, maxDate)}
            disabled={disabled}
            onChange={(event) => {
              if (presetValue == null) setInternalPreset("");
              onPresetChange?.("");
              onChange({ ...value, startDate: event.target.value || null });
            }}
            controlSize="sm"
          />
          <Input
            type="date"
            label={endLabel}
            value={value.endDate ?? ""}
            min={laterDate(value.startDate, minDate)}
            max={maxDate}
            disabled={disabled}
            onChange={(event) => {
              if (presetValue == null) setInternalPreset("");
              onPresetChange?.("");
              onChange({ ...value, endDate: event.target.value || null });
            }}
            controlSize="sm"
          />
        </div>
      )}
      {clearable && dateFieldsVisible && (
        <div className={styles.dateRangeActions}>
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled || (!value.startDate && !value.endDate)}
            onClick={clear}
          >
            {clearLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
