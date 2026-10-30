import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useDraft } from "@shared/lib/useDraft";
import { Input, Section, SettingRow, StickySaveBar } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  AdminBuildSettings,
  AdminInstanceSettings,
  UpdateAdminBuildRequest,
  UpdateAdminInstanceRequest,
} from "@entities/session";
import { failureKey } from "../lib/failure";
import { isLocked } from "../lib/locked";
import {
  RETENTION_MAX,
  RETENTION_MIN,
  TIMEOUT_MAX,
  TIMEOUT_MIN,
  inRange,
  isInsecureUrl,
  validateInstance,
  type InstanceDraft,
} from "../lib/validate";
import { AllLockedNote, UnitInput } from "./parts";
import { settleSaves } from "../lib/saveAll";

export type InstanceFormProps = {
  instance: AdminInstanceSettings;
  build: AdminBuildSettings;
  /** Отказ сервера приходит отклонённым промисом; код ошибки берётся из него. */
  saveInstance: (patch: UpdateAdminInstanceRequest) => Promise<unknown>;
  saveBuild: (patch: UpdateAdminBuildRequest) => Promise<unknown>;
  onSaved?: () => void;
};

type BuildDraft = { minutes: string; days: string };

const INSTANCE_KEYS = ["name", "public_url", "docs_url"] as const;
type InstanceKey = (typeof INSTANCE_KEYS)[number];

/**
 * Раздел «Установка»: название и адрес, пределы сборки. Правки обеих частей
 * сохраняет одна панель внизу страницы.
 */
export const InstanceForm = ({
  instance,
  build,
  saveInstance,
  saveBuild,
  onSaved,
}: InstanceFormProps) => {
  const { t } = useTranslation("adminInstall");
  const uid = useId();
  const lockInstance = (key: InstanceKey) =>
    isLocked(instance.fields, `instance.${key}`);
  const timeoutLocked = isLocked(build.fields, "build.timeout_s");
  const daysLocked = isLocked(build.fields, "build.artifact_retention_days");

  const inst = useDraft<InstanceDraft>(
    {
      name: instance.name,
      public_url: instance.public_url,
      docs_url: instance.docs_url ?? "",
    },
    (key) => !lockInstance(key),
  );
  const bld = useDraft<BuildDraft>(
    {
      minutes: String(Math.round(build.timeout_s / 60)),
      days: String(build.artifact_retention_days),
    },
    (key) => (key === "minutes" ? !timeoutLocked : !daysLocked),
  );
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const issues = validateInstance(inst.value);
  const instanceIssue = (key: InstanceKey): string | undefined => {
    const code = issues[key];
    return code && !lockInstance(key) && (touched || inst.isChanged(key))
      ? t(`instance.issue.${code}`)
      : undefined;
  };
  const minutesBad =
    bld.isChanged("minutes") &&
    !inRange(bld.value.minutes, TIMEOUT_MIN, TIMEOUT_MAX);
  const daysBad =
    bld.isChanged("days") &&
    !inRange(bld.value.days, RETENTION_MIN, RETENTION_MAX);
  const invalid =
    inst.changed.some((key) => issues[key] !== undefined) ||
    minutesBad ||
    daysBad;
  const dirtyCount = inst.changed.length + bld.changed.length;

  const discard = () => {
    inst.reset();
    bld.reset();
    setTouched(false);
    setFailure(null);
  };

  const save = async () => {
    setTouched(true);
    if (dirtyCount === 0 || invalid || busy) return;
    setBusy(true);
    setFailure(null);
    const pick = (key: InstanceKey): string | null =>
      inst.isChanged(key) ? inst.value[key].trim() : null;
    const result = await settleSaves([
      inst.changed.length > 0 && {
        run: () =>
          saveInstance({
            name: pick("name"),
            public_url: pick("public_url"),
            docs_url: pick("docs_url"),
          }),
        done: inst.reset,
      },
      bld.changed.length > 0 && {
        run: () =>
          saveBuild({
            timeout_s: bld.isChanged("minutes")
              ? Number(bld.value.minutes) * 60
              : null,
            artifact_retention_days: bld.isChanged("days")
              ? Number(bld.value.days)
              : null,
            // Личные раннеры правит отдельная строка настроек; здесь их не трогаем.
            personal_runners_enabled: null,
            personal_runner_wait_s: null,
            personal_runners_max_per_user: null,
          }),
        done: bld.reset,
      },
    ]);
    setBusy(false);
    if (result === null) {
      setTouched(false);
      onSaved?.();
    } else {
      setFailure(t(failureKey(result)));
    }
  };

  const textRow = (
    key: InstanceKey,
    label: string,
    hint: string,
    extra: { placeholder?: string; inputMode?: "url"; maxLength?: number },
    below?: React.ReactNode,
  ) => {
    const error = instanceIssue(key);
    return (
      <SettingRow
        label={label}
        hint={hint}
        htmlFor={`${uid}-${key}`}
        locked={lockInstance(key)}
        align="stretch"
        testId={`instance-${key}`}
      >
        <div className="adm-fields">
          <Input
            id={`${uid}-${key}`}
            value={inst.value[key]}
            locked={lockInstance(key)}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => {
              inst.set({ [key]: e.target.value });
            }}
            {...extra}
            {...(error ? { error } : {})}
          />
          {below}
        </div>
      </SettingRow>
    );
  };

  const urlChanged = inst.isChanged("public_url");

  return (
    <form
      noValidate
      className="flex flex-col"
      style={{ gap: 16, flex: 1 }}
      data-testid="instance-form"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        void save();
      }}
    >
      <Section
        id="admin-instance"
        testId="admin-instance"
        title={t("instance.title")}
        description={t("instance.sub")}
        footer={INSTANCE_KEYS.every(lockInstance) ? <AllLockedNote /> : null}
      >
        {textRow("name", t("instance.name"), t("instance.nameHint"), {
          maxLength: 120,
        })}
        {textRow(
          "public_url",
          t("instance.publicUrl"),
          t("instance.publicUrlHint"),
          { placeholder: "https://studio.example.org", inputMode: "url" },
          urlChanged && !issues.public_url ? (
            <>
              {isInsecureUrl(inst.value.public_url) && (
                <Notice tone="warn" text={t("instance.insecure")} />
              )}
              <div data-testid="instance-url-impact">
                <Notice tone="info" text={t("instance.urlImpact")} />
              </div>
            </>
          ) : null,
        )}
        {textRow("docs_url", t("instance.docsUrl"), t("instance.docsUrlHint"), {
          placeholder: "https://docs.example.org",
          inputMode: "url",
        })}
      </Section>

      <Section
        id="admin-build"
        testId="admin-build"
        title={t("build.title")}
        description={t("build.sub")}
        footer={timeoutLocked && daysLocked ? <AllLockedNote /> : null}
      >
        <div data-testid="build-form" style={{ display: "contents" }}>
          <SettingRow
            label={t("build.timeout")}
            hint={
              <>
                {t("build.timeoutHint", {
                  min: TIMEOUT_MIN,
                  max: TIMEOUT_MAX,
                })}{" "}
                <Link to="/admin/quotas" className="adm-hint-link">
                  {t("build.toQuotas")}
                </Link>
              </>
            }
            htmlFor={`${uid}-timeout`}
            locked={timeoutLocked}
            testId="build-timeout"
          >
            <div className="adm-fields" style={{ alignItems: "flex-end" }}>
              <UnitInput
                id={`${uid}-timeout`}
                unit={t("build.minutesUnit")}
                value={bld.value.minutes}
                locked={timeoutLocked}
                aria-invalid={minutesBad || undefined}
                onChange={(e) => {
                  bld.set({ minutes: e.target.value });
                }}
              />
              {minutesBad && (
                <p className="adm-field-error" role="alert">
                  {t("build.issue.range", {
                    min: TIMEOUT_MIN,
                    max: TIMEOUT_MAX,
                  })}
                </p>
              )}
            </div>
          </SettingRow>
          <SettingRow
            label={t("build.retention")}
            hint={t("build.retentionHint", {
              min: RETENTION_MIN,
              max: RETENTION_MAX,
            })}
            htmlFor={`${uid}-days`}
            locked={daysLocked}
            testId="build-retention"
          >
            <div className="adm-fields" style={{ alignItems: "flex-end" }}>
              <UnitInput
                id={`${uid}-days`}
                unit={t("build.daysUnit")}
                value={bld.value.days}
                locked={daysLocked}
                aria-invalid={daysBad || undefined}
                onChange={(e) => {
                  bld.set({ days: e.target.value });
                }}
              />
              {daysBad && (
                <p className="adm-field-error" role="alert">
                  {t("build.issue.range", {
                    min: RETENTION_MIN,
                    max: RETENTION_MAX,
                  })}
                </p>
              )}
            </div>
          </SettingRow>
        </div>
      </Section>

      <StickySaveBar
        dirtyCount={dirtyCount}
        busy={busy}
        saveDisabled={invalid}
        error={failure}
        invalidHint={invalid ? t("fixFields") : null}
        onSave={() => {
          void save();
        }}
        onDiscard={discard}
      />
    </form>
  );
};
