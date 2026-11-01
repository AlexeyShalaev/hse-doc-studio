import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Section, Select, SettingRow } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import type { UpdateSettings } from "../api/schemas";
import { failureKey, type UpdateFailure } from "../lib/failure";
import {
  settingsDraftOf,
  settingsFromDraft,
  type SettingsDraft,
  type SettingsProblem,
} from "../lib/settingsDraft";

const DAYS = [0, 1, 2, 3, 4, 5, 6] as const;

export type PolicyPanelProps = {
  settings: UpdateSettings;
  executor: "compose" | "none";
  saving: boolean;
  failure: UpdateFailure | null;
  onSave: (body: UpdateSettings) => void;
};

/** Политика, предел шага версии, окно обслуживания (UTC), бэкап и проверка образа. */
export const PolicyPanel = ({
  settings,
  executor,
  saving,
  failure,
  onSave,
}: PolicyPanelProps) => {
  const { t } = useTranslation("adminUpdates");
  const initial = settingsDraftOf(settings);
  const [draft, setDraft] = useState<SettingsDraft>(initial);
  const [problem, setProblem] = useState<SettingsProblem | null>(null);
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);
  const set = (patch: Partial<SettingsDraft>) => {
    setDraft({ ...draft, ...patch });
  };
  const bad = (name: SettingsProblem) =>
    problem === name || failure?.field === name;
  const hint = (name: SettingsProblem, normal: string) =>
    bad(name) ? t(`policy.invalid.${name}`) : normal;

  return (
    <Section
      title={t("policy.title")}
      description={t("policy.lead")}
      testId="update-policy"
      footer={
        <div className="flex items-center" style={{ gap: 12 }}>
          <Button
            size="sm"
            disabled={!changed || saving}
            data-testid="update-policy-save"
            onClick={() => {
              const result = settingsFromDraft(draft);
              if ("problem" in result) {
                setProblem(result.problem);
                return;
              }
              setProblem(null);
              onSave(result.body);
            }}
          >
            {t("policy.save")}
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
        label={t("policy.mode.label")}
        hint={t(`policy.mode.hint.${draft.policy}`)}
        htmlFor="up-policy"
      >
        <Select
          id="up-policy"
          ariaLabel={t("policy.mode.label")}
          value={draft.policy}
          onValueChange={(value) => {
            set({ policy: value as SettingsDraft["policy"] });
          }}
          options={(["off", "notify", "auto"] as const).map((value) => ({
            value,
            label: t(`policy.mode.options.${value}`),
            disabled: value === "auto" && executor === "none",
          }))}
        />
      </SettingRow>
      <SettingRow
        label={t("policy.bump.label")}
        hint={t("policy.bump.hint")}
        htmlFor="up-bump"
      >
        <Select
          id="up-bump"
          ariaLabel={t("policy.bump.label")}
          value={draft.maxBump}
          onValueChange={(value) => {
            set({ maxBump: value as SettingsDraft["maxBump"] });
          }}
          options={(["patch", "minor"] as const).map((value) => ({
            value,
            label: t(`policy.bump.options.${value}`),
          }))}
        />
      </SettingRow>
      <SettingRow
        label={t("policy.days.label")}
        hint={hint("window_days", t("policy.days.hint"))}
      >
        <div
          className="flex"
          style={{ gap: 6, flexWrap: "wrap" }}
          role="group"
          aria-label={t("policy.days.label")}
        >
          {DAYS.map((day) => {
            const on = draft.days.includes(day);
            return (
              <Button
                key={day}
                size="sm"
                type="button"
                variant={on ? "primary" : "ghost"}
                aria-pressed={on}
                data-testid={`update-day-${String(day)}`}
                onClick={() => {
                  set({
                    days: on
                      ? draft.days.filter((d) => d !== day)
                      : [...draft.days, day].sort(),
                  });
                }}
              >
                {t(`policy.days.short.${String(day)}`)}
              </Button>
            );
          })}
        </div>
      </SettingRow>
      <SettingRow
        label={t("policy.start.label")}
        hint={hint("window_start_min", t("policy.start.hint"))}
        htmlFor="up-start"
      >
        <Input
          id="up-start"
          type="time"
          value={draft.start}
          onChange={(e) => {
            set({ start: e.target.value });
          }}
          data-testid="update-start"
        />
      </SettingRow>
      <SettingRow
        label={t("policy.length.label")}
        hint={hint("window_minutes", t("policy.length.hint"))}
        htmlFor="up-length"
      >
        <span className="ops-unit-field">
          <Input
            id="up-length"
            type="number"
            min={0.25}
            max={24}
            step={0.25}
            value={draft.hours}
            onChange={(e) => {
              set({ hours: e.target.value });
            }}
            data-testid="update-length"
          />
          <span className="ops-unit">{t("units.h")}</span>
        </span>
      </SettingRow>
      <SettingRow
        label={t("policy.backup.label")}
        hint={t("policy.backup.hint")}
        htmlFor="up-backup"
      >
        <Switch
          id="up-backup"
          checked={draft.backupFirst}
          onChange={(backupFirst) => {
            set({ backupFirst });
          }}
          testId="update-backup-first"
        />
      </SettingRow>
      <SettingRow
        label={t("policy.verify.label")}
        hint={t(`policy.verify.hint.${draft.verify}`)}
        htmlFor="up-verify"
      >
        <Select
          id="up-verify"
          ariaLabel={t("policy.verify.label")}
          value={draft.verify}
          onValueChange={(value) => {
            set({ verify: value as SettingsDraft["verify"] });
          }}
          options={(["digest", "cosign", "none"] as const).map((value) => ({
            value,
            label: t(`policy.verify.options.${value}`),
          }))}
        />
      </SettingRow>
      <SettingRow
        label={t("policy.notify.label")}
        hint={t("policy.notify.hint")}
        htmlFor="up-notify"
      >
        <Switch
          id="up-notify"
          checked={draft.notifyAdmins}
          onChange={(notifyAdmins) => {
            set({ notifyAdmins });
          }}
          testId="update-notify"
        />
      </SettingRow>
    </Section>
  );
};
