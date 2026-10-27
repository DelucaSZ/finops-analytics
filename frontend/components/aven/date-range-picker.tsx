"use client";

import { useState, type HTMLAttributes } from "react";
import { Button, Input, Select } from "@/components/ui";
import styles from "./product-components.module.css";
import type { DateRangePreset, DateRangeValue } from "./types";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
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
  clearLabel?: string;
  disabled?: boolean;
  clearable?: boolean;
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
  clearLabel = "Clear dates",
  disabled = false,
  clearable = true,
  className,
  ...props
}: DateRangePickerProps) {
  const [internalPreset, setInternalPreset] = useState("");
  const activePreset = presetValue ?? internalPreset;

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
    <div className={classNames(styles.dateRangePicker, className)} {...props}>
      {presets.length > 0 && (
        <Select
          label={presetLabel}
          placeholder="Choose a period"
          options={presets.map((preset) => ({ value: preset.value, label: preset.label }))}
          value={activePreset}
          disabled={disabled}
          onChange={(event) => setPreset(event.target.value)}
          controlSize="sm"
        />
      )}
      <div className={styles.dateRangeFields}>
        <Input
          type="date"
          label={startLabel}
          value={value.startDate ?? ""}
          max={value.endDate ?? undefined}
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
          min={value.startDate ?? undefined}
          disabled={disabled}
          onChange={(event) => {
            if (presetValue == null) setInternalPreset("");
            onPresetChange?.("");
            onChange({ ...value, endDate: event.target.value || null });
          }}
          controlSize="sm"
        />
      </div>
      {clearable && (
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
