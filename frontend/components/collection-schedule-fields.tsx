import { formatDate } from "@/lib/api";
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
        <label className="check-label span-2">
          <input
            type="checkbox"
            checked={scheduleEnabled}
            onChange={(event) => onScheduleEnabledChange(event.target.checked)}
          />
          Ativar coleta automática
        </label>
        <p className="span-2 account-form-note">
          Quando ativado, o DeepOps executará automaticamente a coleta desta conta no intervalo selecionado.
        </p>
        <label>
          Intervalo de coleta
          <select
            value={scanIntervalHours}
            disabled={disabled || !scheduleEnabled}
            onChange={(event) => onIntervalChange(Number(event.target.value))}
            aria-describedby={error ? "schedule-interval-error" : undefined}
          >
            {SCHEDULE_INTERVAL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          {error && <span id="schedule-interval-error" className="field-error">{error}</span>}
        </label>
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
