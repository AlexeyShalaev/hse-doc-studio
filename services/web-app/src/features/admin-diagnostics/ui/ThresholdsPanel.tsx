import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Section, SettingRow } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import type { AdminDiagnostics } from "@entities/session";
import {
  bodyOf,
  defaultsDraft,
  draftOf,
  misordered,
  outOfRange,
  THRESHOLD_GROUPS,
  type Draft,
} from "../lib/thresholds";

export type ThresholdsPanelProps = {
  data: AdminDiagnostics;
  saving: boolean;
  failed: boolean;
  onSave: (values: Record<string, number>, notify: boolean) => void;
};

/** Пороги проверок и уведомлений. Пороги места на диске правятся в «Хранении данных». */
export const ThresholdsPanel = ({
  data,
  saving,
  failed,
  onSave,
}: ThresholdsPanelProps) => {
  const { t } = useTranslation("adminDiagnostics");
  const initial = draftOf(data.thresholds);
  const [draft, setDraft] = useState<Draft>(initial);
  const [notify, setNotify] = useState(data.notify);
  const range = new Set(outOfRange(draft, data.thresholds));
  const order = new Set(misordered(draft));
  const invalid = range.size > 0 || order.size > 0;
  const changed =
    JSON.stringify(draft) !== JSON.stringify(initial) || notify !== data.notify;
  const byName = Object.fromEntries(data.thresholds.map((th) => [th.name, th]));

  return (
    <Section
      title={t("thresholds.title")}
      description={t("thresholds.lead")}
      testId="diag-thresholds"
      footer={
        <div className="flex items-center" style={{ gap: 12 }}>
          <Button
            size="sm"
            disabled={!changed || invalid || saving}
            data-testid="diag-thresholds-save"
            onClick={() => {
              onSave(bodyOf(draft), notify);
            }}
          >
            {t("thresholds.save")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            data-testid="diag-thresholds-reset"
            onClick={() => {
              setDraft(defaultsDraft(data.thresholds));
              setNotify(true);
            }}
          >
            {t("thresholds.reset")}
          </Button>
          {invalid && (
            <span className="form-hint" data-testid="diag-thresholds-invalid">
              {t("thresholds.invalid")}
            </span>
          )}
          {failed && (
            <span className="form-hint" data-testid="diag-thresholds-failed">
              {t("thresholds.saveFailed")}
            </span>
          )}
        </div>
      }
    >
      {THRESHOLD_GROUPS.map((group) => (
        <div key={group.id}>
          {group.names.map((name) => {
            const th = byName[name];
            if (!th) return null;
            return (
              <SettingRow
                key={name}
                label={t(`thresholds.name.${name}`)}
                hint={
                  range.has(name) || order.has(name)
                    ? t("thresholds.rowInvalid", { min: th.min, max: th.max })
                    : t(`thresholds.hint.${name}`, {
                        defaultValue: "",
                        value: th.default,
                      })
                }
                htmlFor={`diag-th-${name}`}
              >
                <span className="ops-unit-field">
                  <Input
                    id={`diag-th-${name}`}
                    type="number"
                    min={th.min}
                    max={th.max}
                    value={draft[name] ?? ""}
                    onChange={(e) => {
                      setDraft({ ...draft, [name]: e.target.value });
                    }}
                    data-testid={`diag-th-${name}`}
                  />
                  <span className="ops-unit">
                    {t(`thresholds.unit.${name}`, { defaultValue: "" })}
                  </span>
                </span>
              </SettingRow>
            );
          })}
        </div>
      ))}
      <SettingRow
        label={t("thresholds.notify.label")}
        hint={t("thresholds.notify.hint")}
        htmlFor="diag-notify"
      >
        <Switch id="diag-notify" checked={notify} onChange={setNotify} />
      </SettingRow>
    </Section>
  );
};
