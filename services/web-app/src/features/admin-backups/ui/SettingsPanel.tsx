import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Section, Select, SettingRow } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import type { BackupStatus } from "../api/schemas";
import { failureKey, type BackupFailure } from "../lib/failure";
import {
  settingsDraftOf,
  settingsFromDraft,
  type SettingsDraft,
  type SettingsProblem,
} from "../lib/settingsDraft";
import type { SettingsBody } from "../api/schemas";

export type SettingsPanelProps = {
  status: BackupStatus;
  saving: boolean;
  failure: BackupFailure | null;
  onSave: (body: SettingsBody) => void;
};

/** Расписание, хранение и шифрование. Парольная фраза обратно не показывается. */
export const SettingsPanel = ({
  status,
  saving,
  failure,
  onSave,
}: SettingsPanelProps) => {
  const { t, i18n } = useTranslation("adminBackups");
  const initial = settingsDraftOf(status.settings);
  const [draft, setDraft] = useState<SettingsDraft>(initial);
  const [problem, setProblem] = useState<SettingsProblem | null>(null);
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);
  const set = (patch: Partial<SettingsDraft>) => {
    setDraft({ ...draft, ...patch });
  };
  const bad = (name: SettingsProblem) =>
    problem === name || failure?.field === name;
  const hint = (name: SettingsProblem, normal: string) =>
    bad(name) ? t(`settings.invalid.${name}`) : normal;
  const next = status.next_run_at
    ? new Date(status.next_run_at).toLocaleString(i18n.language)
    : null;

  return (
    <Section
      title={t("settings.title")}
      description={t("settings.lead")}
      testId="backup-settings"
      footer={
        <div className="flex items-center" style={{ gap: 12 }}>
          <Button
            size="sm"
            disabled={!changed || saving}
            data-testid="backup-settings-save"
            onClick={() => {
              const result = settingsFromDraft(
                draft,
                status.settings.passphrase_set,
              );
              if ("problem" in result) {
                setProblem(result.problem);
                return;
              }
              setProblem(null);
              onSave(result.body);
            }}
          >
            {t("settings.save")}
          </Button>
          {failure && !failure.field && (
            <span
              role="alert"
              style={{ color: "var(--c-err)", fontSize: 12.5 }}
            >
              {t(failureKey(failure.code))}
            </span>
          )}
        </div>
      }
    >
      <SettingRow
        label={t("settings.enabled.label")}
        hint={
          next
            ? t("settings.enabled.next", { at: next })
            : t("settings.enabled.hint")
        }
        htmlFor="bk-enabled"
      >
        <Switch
          id="bk-enabled"
          checked={draft.enabled}
          onChange={(enabled) => {
            set({ enabled });
          }}
          testId="backup-enabled"
        />
      </SettingRow>
      <SettingRow
        label={t("settings.kind.label")}
        hint={t(`settings.kind.hint.${draft.scheduleKind}`)}
        htmlFor="bk-schedule-kind"
      >
        <Select
          id="bk-schedule-kind"
          ariaLabel={t("settings.kind.label")}
          value={draft.scheduleKind}
          onValueChange={(value) => {
            set({ scheduleKind: value as SettingsDraft["scheduleKind"] });
          }}
          options={(["interval", "cron"] as const).map((kind) => ({
            value: kind,
            label: t(`settings.kind.options.${kind}`),
          }))}
        />
      </SettingRow>
      {draft.scheduleKind === "interval" ? (
        <SettingRow
          label={t("settings.interval.label")}
          hint={hint("interval_hours", t("settings.interval.hint"))}
          htmlFor="bk-interval"
        >
          <span className="ops-unit-field">
            <Input
              id="bk-interval"
              type="number"
              min={1}
              value={draft.intervalHours}
              onChange={(e) => {
                set({ intervalHours: e.target.value });
              }}
              data-testid="backup-interval"
            />
            <span className="ops-unit">{t("settings.units.h")}</span>
          </span>
        </SettingRow>
      ) : (
        <SettingRow
          label={t("settings.cron.label")}
          hint={hint("cron", t("settings.cron.hint"))}
          htmlFor="bk-cron"
          layout="stacked"
        >
          <Input
            id="bk-cron"
            value={draft.cron}
            placeholder="0 3 * * *"
            onChange={(e) => {
              set({ cron: e.target.value });
            }}
            data-testid="backup-cron"
          />
        </SettingRow>
      )}
      <SettingRow
        label={t("settings.keepLast.label")}
        hint={hint("keep_last", t("settings.keepLast.hint"))}
        htmlFor="bk-keep-last"
      >
        <Input
          id="bk-keep-last"
          type="number"
          min={0}
          value={draft.keepLast}
          onChange={(e) => {
            set({ keepLast: e.target.value });
          }}
          data-testid="backup-keep-last"
        />
      </SettingRow>
      <SettingRow
        label={t("settings.keepDays.label")}
        hint={hint("keep_days", t("settings.keepDays.hint"))}
        htmlFor="bk-keep-days"
      >
        <span className="ops-unit-field">
          <Input
            id="bk-keep-days"
            type="number"
            min={0}
            value={draft.keepDays}
            onChange={(e) => {
              set({ keepDays: e.target.value });
            }}
            data-testid="backup-keep-days"
          />
          <span className="ops-unit">{t("settings.units.d")}</span>
        </span>
      </SettingRow>
      <SettingRow
        label={t("settings.encryption.label")}
        hint={t(`settings.encryption.hint.${draft.encryptionMode}`)}
        htmlFor="bk-encryption"
      >
        <Select
          id="bk-encryption"
          ariaLabel={t("settings.encryption.label")}
          value={draft.encryptionMode}
          onValueChange={(value) => {
            set({ encryptionMode: value as SettingsDraft["encryptionMode"] });
          }}
          options={(["installation", "passphrase"] as const).map((mode) => ({
            value: mode,
            label: t(`settings.encryption.options.${mode}`),
          }))}
        />
      </SettingRow>
      {draft.encryptionMode === "passphrase" && (
        <SettingRow
          label={t("settings.passphrase.label")}
          hint={hint(
            "passphrase",
            status.settings.passphrase_set
              ? t("settings.passphrase.kept")
              : t("settings.passphrase.hint"),
          )}
          htmlFor="bk-passphrase"
          layout="stacked"
        >
          <Input
            id="bk-passphrase"
            type="password"
            autoComplete="new-password"
            value={draft.passphrase}
            placeholder={status.settings.passphrase_set ? "••••••••••••" : ""}
            onChange={(e) => {
              set({ passphrase: e.target.value });
            }}
            data-testid="backup-passphrase"
          />
        </SettingRow>
      )}
      <SettingRow
        label={t("settings.notify.label")}
        hint={t("settings.notify.hint")}
        htmlFor="bk-notify"
      >
        <Switch
          id="bk-notify"
          checked={draft.notifyAdmins}
          onChange={(notifyAdmins) => {
            set({ notifyAdmins });
          }}
        />
      </SettingRow>
    </Section>
  );
};
