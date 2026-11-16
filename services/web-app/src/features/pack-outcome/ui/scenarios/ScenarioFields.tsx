import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { PackOutcome } from "@entities/pack-studio";
import { Input, Select, Textarea } from "@shared/ui";
import {
  SCENARIO_LANGS,
  freeId,
  idProblem,
  seriesOf,
  slugify,
  type ScenarioForm,
  type VersionsMode,
} from "../../lib/scenarios";
import { AssertionsEditor } from "./AssertionsEditor";

export type FieldErrors = Partial<
  Record<"id" | "name" | "versions" | "assertions", string>
>;

type ScenarioFieldsProps = {
  form: ScenarioForm;
  onChange: (next: ScenarioForm) => void;
  /** `edit`: имя файла не меняется (это id сценария). */
  mode: "create" | "edit" | "duplicate";
  version: string;
  /** Имена файлов, которые заняты: из них подбирается свободное. */
  taken: ReadonlySet<string>;
  /** Результат, из которого берутся готовые утверждения. */
  outcome: PackOutcome | undefined;
  /** В файле уже есть снимок: его можно сохранить как есть или записать заново. */
  hadSnapshot: boolean;
  errors: FieldErrors;
  disabled?: boolean;
};

/**
 * Поля сценария: название и описание (ru и en), имя файла, на какие версии распространяется,
 * что запомнить как ожидаемый результат (снимок и (или) утверждения). Форма управляемая, запись
 * и ошибки сервера остаются у окна.
 */
export const ScenarioFields = ({
  form,
  onChange,
  mode,
  version,
  taken,
  outcome,
  hadSnapshot,
  errors,
  disabled,
}: ScenarioFieldsProps) => {
  const { t } = useTranslation("packOutcome");
  const uid = useId();
  // Пока имя файла не правили руками, оно следует за названием.
  const idTouched = useRef(mode === "edit");
  const series = seriesOf(version);

  const setName = (lang: "ru" | "en", value: string) => {
    const name = { ...form.name, [lang]: value };
    const next: ScenarioForm = { ...form, name };
    if (!idTouched.current) {
      next.id = freeId(slugify(name.en.trim() || name.ru), taken);
      if (slugify(name.en.trim() || name.ru) === "") next.id = "";
    }
    onChange(next);
  };
  const idError =
    errors.id ??
    (form.id !== "" && idProblem(form.id) === "format"
      ? t("scenarios.fields.idFormat")
      : taken.has(form.id) && mode !== "edit"
        ? t("scenarios.fields.idTaken")
        : undefined);

  const modes: { value: VersionsMode; label: string }[] = [
    { value: "any", label: t("scenarios.versions.any") },
    { value: "this", label: t("scenarios.versions.this", { version }) },
    ...(series
      ? [
          {
            value: "series" as const,
            label: t("scenarios.versions.series", { series }),
          },
        ]
      : []),
    { value: "custom", label: t("scenarios.versions.custom") },
  ];

  return (
    <div className="po-sc-form" data-testid="scenario-fields">
      {SCENARIO_LANGS.map((lang) => (
        <Input
          key={lang}
          id={`${uid}-name-${lang}`}
          label={t("scenarios.fields.name", { lang: lang.toUpperCase() })}
          value={form.name[lang]}
          disabled={disabled}
          maxLength={200}
          {...(lang === "ru" && errors.name ? { error: errors.name } : {})}
          data-testid={`scenario-name-${lang}`}
          onChange={(event) => {
            setName(lang, event.target.value);
          }}
        />
      ))}
      {SCENARIO_LANGS.map((lang) => (
        <Textarea
          key={lang}
          id={`${uid}-desc-${lang}`}
          label={t("scenarios.fields.description", {
            lang: lang.toUpperCase(),
          })}
          rows={2}
          value={form.description[lang]}
          disabled={disabled}
          maxLength={1000}
          data-testid={`scenario-description-${lang}`}
          onChange={(event) => {
            onChange({
              ...form,
              description: { ...form.description, [lang]: event.target.value },
            });
          }}
        />
      ))}
      <Input
        id={`${uid}-id`}
        label={t("scenarios.fields.id")}
        hint={t("scenarios.fields.idHint")}
        value={form.id}
        isMono
        disabled={disabled}
        readOnly={mode === "edit"}
        maxLength={64}
        {...(idError ? { error: idError } : {})}
        data-testid="scenario-id"
        onChange={(event) => {
          idTouched.current = true;
          onChange({ ...form, id: event.target.value });
        }}
      />
      <div className="field">
        <label htmlFor={`${uid}-versions`}>
          {t("scenarios.fields.versions")}
        </label>
        <Select
          id={`${uid}-versions`}
          ariaLabel={t("scenarios.fields.versions")}
          value={form.versionsMode}
          isDisabled={disabled === true}
          options={modes}
          onValueChange={(next) => {
            onChange({ ...form, versionsMode: next as VersionsMode });
          }}
        />
        {form.versionsMode === "custom" && (
          <Input
            aria-label={t("scenarios.versions.customLabel")}
            placeholder="2026.1.*, 2026.2.1"
            value={form.versionsCustom}
            isMono
            disabled={disabled}
            hint={t("scenarios.versions.customHint")}
            {...(errors.versions ? { error: errors.versions } : {})}
            data-testid="scenario-versions-custom"
            onChange={(event) => {
              onChange({ ...form, versionsCustom: event.target.value });
            }}
          />
        )}
        {form.versionsMode !== "custom" && errors.versions && (
          <p className="text-xs text-c-err" role="alert">
            {errors.versions}
          </p>
        )}
      </div>
      <fieldset className="po-sc-expect" disabled={disabled}>
        <legend>{t("scenarios.expect.title")}</legend>
        <label className="po-check">
          <input
            type="checkbox"
            checked={form.snapshot}
            data-testid="scenario-snapshot"
            onChange={(event) => {
              onChange({
                ...form,
                snapshot: event.target.checked,
                recordSnapshot: event.target.checked && !hadSnapshot,
              });
            }}
          />
          <span>
            {t("scenarios.expect.snapshot")}
            <span className="po-in-hint">
              {t("scenarios.expect.snapshotHint")}
            </span>
          </span>
        </label>
        {form.snapshot && hadSnapshot && (
          <label className="po-check po-check-sub">
            <input
              type="checkbox"
              checked={form.recordSnapshot}
              data-testid="scenario-snapshot-refresh"
              onChange={(event) => {
                onChange({ ...form, recordSnapshot: event.target.checked });
              }}
            />
            <span>{t("scenarios.expect.refresh")}</span>
          </label>
        )}
        <p className="po-sc-legend">{t("scenarios.expect.assertions")}</p>
        <AssertionsEditor
          value={form.assertions}
          outcome={outcome}
          disabled={disabled}
          onChange={(assertions) => {
            onChange({ ...form, assertions });
          }}
        />
        {errors.assertions && (
          <p className="text-xs text-c-err" role="alert">
            {errors.assertions}
          </p>
        )}
      </fieldset>
    </div>
  );
};
