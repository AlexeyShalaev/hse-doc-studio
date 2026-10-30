import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useDraft } from "@shared/lib/useDraft";
import {
  Button,
  Input,
  Modal,
  Section,
  SettingRow,
  StickySaveBar,
} from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
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
type PersonalDraft = { enabled: boolean; wait: string; max: string };

// Пределы личных раннеров: те же, что проверяет сервер (раздел 3.7 спецификации).
const WAIT_MIN = 0;
const WAIT_MAX = 60;
const PER_USER_MIN = 1;
const PER_USER_MAX = 20;

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
  // Сервер без личных раннеров этих полей не отдаёт: тогда и строк нет.
  const personalKnown = build.personal_runners_enabled !== undefined;
  const enabledLocked = isLocked(build.fields, "runners.personal_enabled");
  const waitLocked = isLocked(build.fields, "runners.personal_wait_s");
  const maxLocked = isLocked(build.fields, "runners.personal_max_per_user");
  const prs = useDraft<PersonalDraft>(
    {
      enabled: build.personal_runners_enabled ?? true,
      wait: String(build.personal_runner_wait_s ?? 5),
      max: String(build.personal_runners_max_per_user ?? 5),
    },
    (key) =>
      personalKnown &&
      (key === "enabled"
        ? !enabledLocked
        : key === "wait"
          ? !waitLocked
          : !maxLocked),
  );
  const [confirmOff, setConfirmOff] = useState(false);
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
  const waitBad =
    prs.isChanged("wait") && !inRange(prs.value.wait, WAIT_MIN, WAIT_MAX);
  const maxBad =
    prs.isChanged("max") && !inRange(prs.value.max, PER_USER_MIN, PER_USER_MAX);
  const invalid =
    inst.changed.some((key) => issues[key] !== undefined) ||
    minutesBad ||
    daysBad ||
    waitBad ||
    maxBad;
  const dirtyCount =
    inst.changed.length + bld.changed.length + prs.changed.length;

  const discard = () => {
    inst.reset();
    bld.reset();
    prs.reset();
    setTouched(false);
    setFailure(null);
  };

  // Выключение личных раннеров меняет жизнь всех их хозяев: сначала подтверждение.
  const turningOff = prs.isChanged("enabled") && !prs.value.enabled;

  const save = async (confirmed = false) => {
    setTouched(true);
    if (dirtyCount === 0 || invalid || busy) return;
    if (turningOff && !confirmed) {
      setConfirmOff(true);
      return;
    }
    setConfirmOff(false);
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
      (bld.changed.length > 0 || prs.changed.length > 0) && {
        run: () =>
          saveBuild({
            timeout_s: bld.isChanged("minutes")
              ? Number(bld.value.minutes) * 60
              : null,
            artifact_retention_days: bld.isChanged("days")
              ? Number(bld.value.days)
              : null,
            // Поля личных раннеров уходят только серверу, который их знает:
            // старый сервер отверг бы лишние ключи.
            ...(personalKnown
              ? {
                  personal_runners_enabled: prs.isChanged("enabled")
                    ? prs.value.enabled
                    : null,
                  personal_runner_wait_s: prs.isChanged("wait")
                    ? Number(prs.value.wait)
                    : null,
                  personal_runners_max_per_user: prs.isChanged("max")
                    ? Number(prs.value.max)
                    : null,
                }
              : {}),
          }),
        done: () => {
          bld.reset();
          prs.reset();
        },
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
        footer={
          timeoutLocked &&
          daysLocked &&
          (!personalKnown || (enabledLocked && waitLocked && maxLocked)) ? (
            <AllLockedNote />
          ) : null
        }
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
          {personalKnown && (
            <>
              <SettingRow
                label={t("build.personal.enabled")}
                hint={t("build.personal.enabledHint")}
                htmlFor={`${uid}-personal`}
                locked={enabledLocked}
                testId="build-personal-enabled"
              >
                <Switch
                  id={`${uid}-personal`}
                  checked={prs.value.enabled}
                  disabled={enabledLocked}
                  onChange={(enabled) => {
                    prs.set({ enabled });
                  }}
                  testId="admin-personal-runners-toggle"
                />
              </SettingRow>
              <SettingRow
                label={t("build.personal.wait")}
                hint={t("build.personal.waitHint", {
                  min: WAIT_MIN,
                  max: WAIT_MAX,
                })}
                htmlFor={`${uid}-wait`}
                locked={waitLocked}
                testId="build-personal-wait"
              >
                <div className="adm-fields" style={{ alignItems: "flex-end" }}>
                  <UnitInput
                    id={`${uid}-wait`}
                    unit={t("build.personal.secondsUnit")}
                    value={prs.value.wait}
                    locked={waitLocked}
                    disabled={!prs.value.enabled && !waitLocked}
                    aria-invalid={waitBad || undefined}
                    onChange={(e) => {
                      prs.set({ wait: e.target.value });
                    }}
                    data-testid="admin-personal-wait-s"
                  />
                  {waitBad && (
                    <p className="adm-field-error" role="alert">
                      {t("build.issue.range", { min: WAIT_MIN, max: WAIT_MAX })}
                    </p>
                  )}
                </div>
              </SettingRow>
              <SettingRow
                label={t("build.personal.max")}
                hint={t("build.personal.maxHint", {
                  min: PER_USER_MIN,
                  max: PER_USER_MAX,
                })}
                htmlFor={`${uid}-max`}
                locked={maxLocked}
                testId="build-personal-max"
              >
                <div className="adm-fields" style={{ alignItems: "flex-end" }}>
                  <UnitInput
                    id={`${uid}-max`}
                    unit={t("build.personal.runnersUnit")}
                    value={prs.value.max}
                    locked={maxLocked}
                    disabled={!prs.value.enabled && !maxLocked}
                    aria-invalid={maxBad || undefined}
                    onChange={(e) => {
                      prs.set({ max: e.target.value });
                    }}
                    data-testid="admin-personal-max"
                  />
                  {maxBad && (
                    <p className="adm-field-error" role="alert">
                      {t("build.issue.range", {
                        min: PER_USER_MIN,
                        max: PER_USER_MAX,
                      })}
                    </p>
                  )}
                </div>
              </SettingRow>
            </>
          )}
        </div>
      </Section>

      <Modal
        isOpen={confirmOff}
        onClose={() => {
          setConfirmOff(false);
        }}
        title={t("build.personal.offTitle")}
        description={t("build.personal.offBody")}
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setConfirmOff(false);
              }}
            >
              {t("build.personal.offCancel")}
            </Button>
            <Button
              type="button"
              variant="danger"
              onClick={() => {
                void save(true);
              }}
              data-testid="admin-personal-off-confirm"
            >
              {t("build.personal.offConfirm")}
            </Button>
          </>
        }
      />

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
