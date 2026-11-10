"use client";

import {useLocale, useTranslations} from "next-intl";
import { Checkbox, Select } from "@/components/ui";
import { formatDate } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import { SCHEDULE_INTERVAL_OPTIONS } from "@/lib/account-scheduling.mjs";

type CollectionScheduleFieldsProps = {
  supported: boolean;
  scheduleEnabled: boolean;
  scanIntervalHours: number;
  nextScanAt?: string | null;
  showNextScan?: boolean;
  disabled?: boolean;
  error?: string;
  onScheduleEnabledChange: (enabled: boolean) => void;
  onIntervalChange: (hours: number) => void;
};

export function CollectionScheduleFields({
  supported,
  scheduleEnabled,
  scanIntervalHours,
  nextScanAt,
  showNextScan = false,
  disabled = false,
  error,
  onScheduleEnabledChange,
  onIntervalChange,
}: CollectionScheduleFieldsProps) {
  const t = useTranslations("settings.schedule");
  const locale = useLocale();
  if (!supported) {
    return (
      <div className="span-2 account-form-note" role="status">
        <strong>{t("title")}</strong><br />
        {t("unsupported")}
      </div>
    );
  }

  return (
    <fieldset className="span-2 account-provider-fieldset" disabled={disabled}>
      <legend>{t("title")}</legend>
      <div className="form-grid">
        <div className="span-2">
          <Checkbox
            checked={scheduleEnabled}
            disabled={disabled}
            label={t("enable")}
            description={t("description", {product: PRODUCT_NAME})}
            onChange={(event) => onScheduleEnabledChange(event.target.checked)}
          />
        </div>
        <Select
          label={t("interval")}
          value={String(scanIntervalHours)}
          disabled={disabled || !scheduleEnabled}
          error={error}
          options={SCHEDULE_INTERVAL_OPTIONS.map((option) => ({
            value: String(option.value),
            label: option.value === 12 ? t("interval12") : option.value === 24 ? t("interval24") : option.value === 168 ? t("interval168") : option.label,
          }))}
          onChange={(event) => onIntervalChange(Number(event.target.value))}
        />
        {showNextScan && scheduleEnabled && (
          <div className="account-form-note">
            <strong>{t("nextExecution")}</strong><br />
            {nextScanAt ? formatDate(nextScanAt, locale) : t("nextUnavailable")}
          </div>
        )}
        {showNextScan && !scheduleEnabled && (
          <div className="account-form-note">
            <strong>{t("disabled")}</strong>
          </div>
        )}
      </div>
    </fieldset>
  );
}
