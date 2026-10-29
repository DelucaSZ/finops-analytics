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
  if (!supported) {
    return (
      <div className="span-2 account-form-note" role="status">
        <strong>Agendamento</strong><br />
        Não implementado para este provider.
      </div>
    );
  }

  return (
    <fieldset className="span-2 account-provider-fieldset" disabled={disabled}>
      <legend>Agendamento</legend>
      <div className="form-grid">
        <div className="span-2">
          <Checkbox
            checked={scheduleEnabled}
            disabled={disabled}
            label="Ativar coleta automática"
            description={`Quando ativado, o ${PRODUCT_NAME} executará automaticamente a coleta desta conta no intervalo selecionado.`}
            onChange={(event) => onScheduleEnabledChange(event.target.checked)}
          />
        </div>
        <Select
          label="Intervalo de coleta"
          value={String(scanIntervalHours)}
          disabled={disabled || !scheduleEnabled}
          error={error}
          options={SCHEDULE_INTERVAL_OPTIONS.map((option) => ({
            value: String(option.value),
            label: option.label,
          }))}
          onChange={(event) => onIntervalChange(Number(event.target.value))}
        />
        {showNextScan && scheduleEnabled && (
          <div className="account-form-note">
            <strong>Próxima execução prevista</strong><br />
            {nextScanAt ? formatDate(nextScanAt) : "Próxima execução ainda não disponível"}
          </div>
        )}
        {showNextScan && !scheduleEnabled && (
          <div className="account-form-note">
            <strong>Coleta automática desativada</strong>
          </div>
        )}
      </div>
    </fieldset>
  );
}
