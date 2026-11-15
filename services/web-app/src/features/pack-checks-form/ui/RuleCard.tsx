import { useState } from "react";
import { ChevronDown, ChevronUp, Save, Trash2, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  PackCheckRule,
  PackChecksOp,
  PackPreviewCheck,
} from "@entities/pack-studio";
import { Check, LocalizedFields } from "@features/pack-submission-form/ui/kit";
import { pickLocalized } from "@shared/lib";
import { Button, Input, Select, Textarea } from "@shared/ui";
import {
  STRUCTURAL_FIELDS,
  fieldText,
  fieldValue,
  getAt,
  setAt,
  typedCheck,
  type Params,
} from "../lib/params";

export type RuleCtx = {
  disabled: boolean;
  documents: readonly string[];
  docName: (doc: string) => string;
  engines: readonly string[];
  structuralChecks: readonly string[];
  categories: readonly string[];
  apply: (ops: PackChecksOp[]) => void;
};

type Draft = {
  rule: PackCheckRule;
  params: Params;
  yaml: string;
};

const draftOf = (rule: PackCheckRule, yaml: string | null): Draft => ({
  rule,
  params: { ...(rule.params ?? {}) },
  yaml: yaml ?? "",
});

const SEVERITIES = ["info", "warn", "err"] as const;

/** Параметры правила: поля известной структурной проверки или текст YAML. */
const ParamsEditor = ({
  ctx,
  draft,
  onChange,
  index,
}: {
  ctx: RuleCtx;
  draft: Draft;
  onChange: (next: Draft) => void;
  index: number;
}) => {
  const { t } = useTranslation("packStudio");
  const typed = typedCheck(draft.rule.engine, draft.params);
  const [texts, setTexts] = useState<Record<string, string>>({});
  if (draft.rule.engine === "structural") {
    const check =
      typeof draft.params.check === "string" ? draft.params.check : "";
    const fields = typed ? (STRUCTURAL_FIELDS[typed] ?? []) : [];
    return (
      <div className="pcf-params" data-testid={`rule-${String(index)}-params`}>
        <div className="field">
          <label>{t("checksForm.rule.check")}</label>
          <Select
            value={check}
            onValueChange={(next) => {
              // Другая проверка: параметры прежней к ней не подходят.
              onChange({ ...draft, params: { check: next } });
            }}
            isDisabled={ctx.disabled}
            ariaLabel={t("checksForm.rule.check")}
            options={[
              ...(check && !ctx.structuralChecks.includes(check)
                ? [{ value: check, label: check }]
                : []),
              ...ctx.structuralChecks.map((name) => ({
                value: name,
                label: t(`checksForm.structural.${name}`, {
                  defaultValue: name,
                }),
              })),
            ]}
          />
        </div>
        {fields.map((f) => {
          const key = f.path.join(".");
          const shown =
            texts[key] ?? fieldText(getAt(draft.params, f.path), f.kind);
          const value = fieldValue(shown, f.kind);
          return (
            <Input
              key={key}
              label={t(`checksForm.param.${key}`, { defaultValue: key })}
              value={shown}
              isMono
              disabled={ctx.disabled}
              {...(value === null
                ? { error: t("checksForm.param.notNumber") }
                : {})}
              onChange={(e) => {
                const text = e.target.value;
                setTexts({ ...texts, [key]: text });
                const parsed = fieldValue(text, f.kind);
                if (parsed !== null) {
                  onChange({
                    ...draft,
                    params: setAt(draft.params, f.path, parsed),
                  });
                }
              }}
              data-testid={`rule-${String(index)}-param-${key}`}
            />
          );
        })}
        {typed && fields.length === 0 && (
          <p className="hint">{t("checksForm.param.none")}</p>
        )}
        {!typed && check && (
          <p className="hint pcf-warn">{t("checksForm.param.unknownCheck")}</p>
        )}
      </div>
    );
  }
  return (
    <div className="pcf-params">
      <Textarea
        label={t("checksForm.rule.paramsYaml")}
        hint={t("checksForm.rule.paramsYamlHint")}
        value={draft.yaml}
        isMono
        rows={Math.min(14, Math.max(3, draft.yaml.split("\n").length + 1))}
        disabled={ctx.disabled}
        onChange={(e) => {
          onChange({ ...draft, yaml: e.target.value });
        }}
        data-testid={`rule-${String(index)}-yaml`}
      />
    </div>
  );
};

export type RuleCardProps = {
  ctx: RuleCtx;
  index: number;
  count: number;
  rule: PackCheckRule;
  paramsYaml: string | null;
  prefix: string;
  findings: readonly PackPreviewCheck[] | undefined;
  /** Сборка с проверками была: правило без находок прошло. */
  checked: boolean;
};

/**
 * Правило проверки карточкой (5.7): id, название и описание ru и en, категория, к каким
 * документам, важность, движок и параметры. Сохраняется кнопкой; рядом находки последней
 * сборки предпросмотра с проверками.
 */
export const RuleCard = ({
  ctx,
  index,
  count,
  rule,
  paramsYaml,
  prefix,
  findings,
  checked,
}: RuleCardProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const [draft, setDraft] = useState(() => draftOf(rule, paramsYaml));
  const [seen, setSeen] = useState({ rule, paramsYaml });
  if (seen.rule !== rule || seen.paramsYaml !== paramsYaml) {
    setSeen({ rule, paramsYaml });
    setDraft(draftOf(rule, paramsYaml));
  }
  const initial = draftOf(rule, paramsYaml);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  const yamlMode = draft.rule.engine !== "structural";
  const all =
    draft.rule.applies_to === null || draft.rule.applies_to === undefined;
  const applies = draft.rule.applies_to ?? [];
  const setRule = (patch: Partial<PackCheckRule>) => {
    setDraft({ ...draft, rule: { ...draft.rule, ...patch } });
  };
  const save = () => {
    const next: PackCheckRule = { ...draft.rule, params: draft.params };
    ctx.apply([
      yamlMode && draft.yaml !== (paramsYaml ?? "")
        ? { op: "set_rule", index, rule: next, params_yaml: draft.yaml }
        : { op: "set_rule", index, rule: next },
    ]);
  };
  const title = pickLocalized(rule.title, i18n.language, rule.id);
  const errors = (findings ?? []).length;
  return (
    <li className="pcf-rule" data-testid={`rule-${String(index)}`}>
      <details>
        <summary className="pcf-rule-summary">
          <span className="pcf-rule-title">{title}</span>
          <code className="mono pcf-id">{rule.id}</code>
          <span className={`ps-mark pcf-sev-${rule.default_severity}`}>
            {t(`checksForm.severity.${rule.default_severity}`)}
          </span>
          {checked && (
            <span
              className={
                errors > 0 ? "ps-mark ps-mark-warn" : "ps-mark ps-mark-ok"
              }
              data-testid={`rule-${String(index)}-result`}
            >
              {errors > 0
                ? t("checksForm.findings", { count: errors })
                : t("checksForm.passed")}
            </span>
          )}
        </summary>
        <div className="pcf-rule-body">
          {(findings ?? []).length > 0 && (
            <ul
              className="pcf-findings"
              data-testid={`rule-${String(index)}-findings`}
            >
              {(findings ?? []).map((f, i) => (
                <li key={`${String(i)}:${f.message}`}>
                  <span className={`ps-mark pcf-sev-${f.severity}`}>
                    {t(`checksForm.severity.${f.severity}`, {
                      defaultValue: f.severity,
                    })}
                  </span>{" "}
                  {f.message}
                  {f.file && (
                    <span className="mono pcf-where">
                      {" "}
                      {f.line !== null ? `${f.file}:${String(f.line)}` : f.file}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <Input
            label={t("checksForm.rule.id")}
            {...(draft.rule.id.startsWith(`${prefix}/`)
              ? {}
              : { hint: t("checksForm.rule.prefixHint", { prefix }) })}
            value={draft.rule.id}
            isMono
            disabled={ctx.disabled}
            onChange={(e) => {
              setRule({ id: e.target.value });
            }}
          />
          <LocalizedFields
            label={t("checksForm.rule.title")}
            value={draft.rule.title}
            disabled={ctx.disabled}
            onChange={(value) => {
              setRule({ title: value });
            }}
          />
          <LocalizedFields
            label={t("checksForm.rule.description")}
            value={draft.rule.description ?? {}}
            disabled={ctx.disabled}
            multiline
            onChange={(value) => {
              setRule({ description: value });
            }}
          />
          <div className="pcf-row">
            <Input
              label={t("checksForm.rule.category")}
              value={draft.rule.category ?? ""}
              list="pcf-categories"
              disabled={ctx.disabled}
              onChange={(e) => {
                setRule({ category: e.target.value || null });
              }}
            />
            <div className="field">
              <label>{t("checksForm.rule.severity")}</label>
              <Select
                value={draft.rule.default_severity}
                onValueChange={(value) => {
                  setRule({
                    default_severity:
                      value as PackCheckRule["default_severity"],
                  });
                }}
                isDisabled={ctx.disabled}
                ariaLabel={t("checksForm.rule.severity")}
                options={SEVERITIES.map((s) => ({
                  value: s,
                  label: t(`checksForm.severity.${s}`),
                }))}
              />
            </div>
            <div className="field">
              <label>{t("checksForm.rule.engine")}</label>
              <Select
                value={draft.rule.engine}
                onValueChange={(engine) => {
                  setDraft({ ...draft, rule: { ...draft.rule, engine } });
                }}
                isDisabled={ctx.disabled}
                ariaLabel={t("checksForm.rule.engine")}
                options={ctx.engines.map((e) => ({
                  value: e,
                  label: t(`checksForm.engine.${e}`, { defaultValue: e }),
                }))}
              />
            </div>
          </div>
          <fieldset className="pcf-applies">
            <legend>{t("checksForm.rule.appliesTo")}</legend>
            <Check
              label={t("checksForm.rule.allDocuments")}
              checked={all}
              disabled={ctx.disabled}
              onChange={(next) => {
                setRule({ applies_to: next ? null : [...ctx.documents] });
              }}
            />
            {!all &&
              ctx.documents.map((doc) => (
                <Check
                  key={doc}
                  label={ctx.docName(doc)}
                  checked={applies.includes(doc)}
                  disabled={ctx.disabled}
                  onChange={(next) => {
                    setRule({
                      applies_to: next
                        ? [...applies, doc]
                        : applies.filter((d) => d !== doc),
                    });
                  }}
                />
              ))}
            {!all &&
              applies
                .filter((doc) => !ctx.documents.includes(doc))
                .map((doc) => (
                  <p className="hint pcf-warn" key={doc}>
                    {t("checksForm.rule.unknownDocument", { doc })}
                  </p>
                ))}
          </fieldset>
          <ParamsEditor
            ctx={ctx}
            draft={draft}
            onChange={setDraft}
            index={index}
          />
          {!ctx.disabled && (
            <div className="pcf-actions">
              <button
                type="button"
                className="icon-btn"
                disabled={index === 0}
                onClick={() => {
                  ctx.apply([{ op: "move_rule", index, to: index - 1 }]);
                }}
                aria-label={t("checksForm.rule.up")}
                title={t("checksForm.rule.up")}
              >
                <ChevronUp size="0.75rem" />
              </button>
              <button
                type="button"
                className="icon-btn"
                disabled={index >= count - 1}
                onClick={() => {
                  ctx.apply([{ op: "move_rule", index, to: index + 1 }]);
                }}
                aria-label={t("checksForm.rule.down")}
                title={t("checksForm.rule.down")}
              >
                <ChevronDown size="0.75rem" />
              </button>
              <Button
                size="xs"
                variant="ghost"
                onClick={() => {
                  ctx.apply([{ op: "remove_rule", index }]);
                }}
                data-testid={`rule-${String(index)}-remove`}
              >
                <Trash2 size="0.6875rem" />
                {t("checksForm.rule.remove")}
              </Button>
              <span className="pcf-spacer" />
              <Button
                size="xs"
                variant="ghost"
                disabled={!dirty}
                onClick={() => {
                  setDraft(initial);
                }}
              >
                <Undo2 size="0.6875rem" />
                {t("checksForm.rule.reset")}
              </Button>
              <Button
                size="xs"
                disabled={!dirty || draft.rule.id.trim() === ""}
                onClick={save}
                data-testid={`rule-${String(index)}-save`}
              >
                <Save size="0.6875rem" />
                {t("checksForm.rule.save")}
              </Button>
            </div>
          )}
        </div>
      </details>
    </li>
  );
};
