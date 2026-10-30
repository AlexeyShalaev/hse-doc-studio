import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@shared/ui";
import type {
  AdminBuildSettings,
  UpdateAdminBuildRequest,
} from "@entities/session";
import type { Failure } from "../lib/failure";
import { isLocked } from "../lib/locked";
import {
  RETENTION_MAX,
  RETENTION_MIN,
  TIMEOUT_MAX,
  TIMEOUT_MIN,
  inRange,
} from "../lib/validate";
import { LockedBadge, SettingsCard } from "./parts";
import { SaveRow } from "./SaveRow";

export type BuildCardProps = {
  settings: AdminBuildSettings;
  pending?: boolean;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (patch: UpdateAdminBuildRequest) => void;
};

/** Раздел «Сборка»: предел длительности сборки и срок хранения результатов. */
export const BuildCard = ({
  settings,
  pending = false,
  failure = null,
  saved = false,
  onSave,
}: BuildCardProps) => {
  const { t } = useTranslation("adminInstall");
  const uid = useId();
  const baseMinutes = String(Math.round(settings.timeout_s / 60));
  const baseDays = String(settings.artifact_retention_days);
  const [minutes, setMinutes] = useState(baseMinutes);
  const [days, setDays] = useState(baseDays);
  const [touched, setTouched] = useState(false);
  const timeoutLocked = isLocked(settings.fields, "build.timeout_s");
  const daysLocked = isLocked(settings.fields, "build.artifact_retention_days");
  const minutesChanged = !timeoutLocked && minutes.trim() !== baseMinutes;
  const daysChanged = !daysLocked && days.trim() !== baseDays;
  const dirty = minutesChanged || daysChanged;
  const minutesBad =
    !timeoutLocked && !inRange(minutes, TIMEOUT_MIN, TIMEOUT_MAX);
  const daysBad = !daysLocked && !inRange(days, RETENTION_MIN, RETENTION_MAX);

  return (
    <SettingsCard
      id="admin-build"
      testId="admin-build"
      title={t("build.title")}
      sub={t("build.sub")}
    >
      <form
        noValidate
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="build-form"
        onSubmit={(e) => {
          e.preventDefault();
          setTouched(true);
          if (!dirty || minutesBad || daysBad || pending) return;
          onSave({
            timeout_s: minutesChanged ? Number(minutes) * 60 : null,
            artifact_retention_days: daysChanged ? Number(days) : null,
          });
        }}
      >
        <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
          <Input
            id={`${uid}-timeout`}
            label={t("build.timeout")}
            hint={t("build.timeoutHint", {
              min: TIMEOUT_MIN,
              max: TIMEOUT_MAX,
            })}
            value={minutes}
            readOnly={timeoutLocked}
            inputMode="numeric"
            onChange={(e) => {
              setMinutes(e.target.value);
            }}
            {...(touched && minutesBad
              ? {
                  error: t("build.issue.range", {
                    min: TIMEOUT_MIN,
                    max: TIMEOUT_MAX,
                  }),
                }
              : {})}
          />
          {timeoutLocked && <LockedBadge testId="locked-build-timeout" />}
        </div>
        <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
          <Input
            id={`${uid}-days`}
            label={t("build.retention")}
            hint={t("build.retentionHint", {
              min: RETENTION_MIN,
              max: RETENTION_MAX,
            })}
            value={days}
            readOnly={daysLocked}
            inputMode="numeric"
            onChange={(e) => {
              setDays(e.target.value);
            }}
            {...(touched && daysBad
              ? {
                  error: t("build.issue.range", {
                    min: RETENTION_MIN,
                    max: RETENTION_MAX,
                  }),
                }
              : {})}
          />
          {daysLocked && <LockedBadge testId="locked-build-retention" />}
        </div>
        <SaveRow
          testId="build"
          dirty={dirty}
          pending={pending}
          failure={failure}
          saved={saved}
          allLocked={timeoutLocked && daysLocked}
        />
      </form>
    </SettingsCard>
  );
};
