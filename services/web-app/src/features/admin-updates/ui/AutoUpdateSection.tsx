import { useTranslation } from "react-i18next";
import { localeTag } from "@shared/lib";
import { Section, SettingRow } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import type { UpdateStatus } from "../api/schemas";
import { failureKey, type UpdateFailure } from "../lib/failure";

export type AutoUpdateSectionProps = {
  data: UpdateStatus;
  pending: boolean;
  failure: UpdateFailure | null;
  onToggle: (enabled: boolean) => void;
};

/**
 * Переключатель автоустановки. Выключенная автоустановка ничего не ставит сама, но проверка релизов и уведомления
 * остаются; состояние хранится на сервере (политика `auto` или `notify`), поэтому переживает перезапуски.
 */
export const AutoUpdateSection = ({
  data,
  pending,
  failure,
  onToggle,
}: AutoUpdateSectionProps) => {
  const { t } = useTranslation("adminUpdates");
  const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
  const off = data.settings.policy === "off";
  const manualOnly = data.executor === "none";
  const state = off ? "off" : data.auto_update_enabled ? "on" : "paused";
  return (
    <Section
      title={t("auto.title")}
      description={t("auto.lead")}
      testId="update-auto"
    >
      <SettingRow
        label={t("auto.label")}
        hint={t(`auto.hint.${state}`)}
        htmlFor="update-auto-switch"
      >
        <Switch
          id="update-auto-switch"
          checked={data.auto_update_enabled}
          disabled={pending || manualOnly}
          onChange={onToggle}
          label={t("auto.label")}
          testId="update-auto-switch"
        />
      </SettingRow>
      <dl className="ops-dl" data-testid="update-auto-status">
        <div>
          <dt>{t("auto.state")}</dt>
          <dd data-testid="update-auto-state">{t(`auto.states.${state}`)}</dd>
        </div>
        <div>
          <dt>{t("version.checked")}</dt>
          <dd data-testid="update-auto-checked">
            {off
              ? t("auto.checksOff")
              : data.checked_at
                ? when(data.checked_at)
                : "—"}
          </dd>
        </div>
      </dl>
      {manualOnly && <p className="form-hint">{t("auto.manualOnly")}</p>}
      {failure && (
        <p
          role="alert"
          style={{ color: "var(--c-err)", fontSize: "0.78125rem" }}
          data-testid="update-auto-failure"
        >
          {t(failureKey(failure.code))}
        </p>
      )}
    </Section>
  );
};
