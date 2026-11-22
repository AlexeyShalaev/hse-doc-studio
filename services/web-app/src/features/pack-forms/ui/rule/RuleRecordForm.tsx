import { useTranslation } from "react-i18next";
import { langName } from "../../lib/langName";
import { asRecord, asString, asStrings } from "../../lib/raw";
import {
  WHEN_CHOICES,
  listOptions,
  selectedOf,
  siblingFields,
  whenChoice,
  whenValue,
  type RuleChange,
  type RuleFormContext,
  type RuleShape,
} from "../../lib/ruleRecord";
import {
  ChipToggles,
  CheckInput,
  CommitInput,
  FormRow,
  SelectInput,
} from "../kit";
import "../packForms.css";

export type RuleRecordFormProps = {
  shape: RuleShape;
  /** Указатель записи в манифесте: на нём держится привязка формы к записи (`data-pf-at`). */
  pointer: string;
  /** Текущее значение записи; `undefined`, если ключа в манифесте нет. */
  value: unknown;
  context: RuleFormContext;
  disabled: boolean;
  /** Правка записана полем: значение или «убрать ключ». */
  onChange: (change: RuleChange) => void;
  testId?: string | undefined;
};

const scalarText = (value: unknown): string =>
  typeof value === "string" ||
  typeof value === "number" ||
  typeof value === "boolean"
    ? String(value)
    : "";

/**
 * Одна запись манифеста целиком: вид работы, состав, языки, галочка, условие показа поля, условие
 * слота подписи, отключённые проверки. Поля те же, что у вкладки «Форма» (ChipToggles, CheckInput,
 * SelectInput, CommitInput); здесь они без остальной формы, чтобы автор правил одно правило и
 * сразу видел последствия на экране «Результат».
 */
export const RuleRecordForm = ({
  shape,
  pointer,
  value,
  context,
  disabled,
  onChange,
  testId,
}: RuleRecordFormProps) => {
  const { t, i18n } = useTranslation("packForms");
  const set = (next: unknown): void => {
    onChange({ type: "set", value: next });
  };
  let body;
  switch (shape.kind) {
    case "list": {
      const all = listOptions(shape.list, context.manifest);
      const names: Record<string, string> = {
        kinds: t("rule.list.kinds"),
        staffing: t("rule.list.staffing"),
        langs: t("rule.list.langs"),
      };
      body = (
        <ChipToggles
          label={names[shape.list] ?? shape.list}
          hint={t("rule.list.hint")}
          options={all.map((v) => ({
            value: v,
            label:
              shape.list === "kinds"
                ? t(`kinds.${v}`, { defaultValue: v })
                : shape.list === "staffing"
                  ? t(`doc.staffingValues.${v}`, { defaultValue: v })
                  : langName(v, i18n.language),
          }))}
          value={selectedOf(value, all)}
          disabled={disabled}
          testId="pf-rule-list"
          onChange={(next) => {
            // Всё выбрано или ничего: ограничения нет, ключ убирается (как у формы документа).
            if (next.length === 0 || next.length === all.length) {
              onChange({ type: "remove" });
            } else set(next);
          }}
        />
      );
      break;
    }
    case "flag":
      body = (
        <CheckInput
          label={t(`rule.flag.${shape.flag}`)}
          hint={t(`rule.flag.${shape.flag}Hint`)}
          checked={value === true}
          disabled={disabled}
          testId="pf-rule-flag"
          onChange={(next) => {
            if (next) set(true);
            else onChange({ type: "remove" });
          }}
        />
      );
      break;
    case "visibleIf": {
      const visible = asRecord(value);
      const field = asString(visible.field);
      const others = siblingFields(context.manifest, pointer);
      body = (
        <div className="pf-grid">
          <FormRow label={t("forms.visibleIf")} hint={t("forms.visibleIfHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("forms.visibleIf")}
                value={field}
                disabled={disabled}
                testId="pf-rule-visible-field"
                options={[
                  { value: "", label: t("forms.always") },
                  ...others.map((o) => ({ value: o, label: o })),
                ]}
                onChange={(next) => {
                  if (next) {
                    set({ field: next, equals: visible.equals ?? true });
                  } else onChange({ type: "remove" });
                }}
              />
            )}
          </FormRow>
          {field !== "" && (
            <FormRow label={t("forms.equals")}>
              {(id) => (
                <CommitInput
                  id={id}
                  ariaLabel={t("forms.equals")}
                  value={scalarText(visible.equals)}
                  disabled={disabled}
                  testId="pf-rule-visible-equals"
                  onCommit={(next) => {
                    set({
                      field,
                      equals:
                        next === "true"
                          ? true
                          : next === "false"
                            ? false
                            : next,
                    });
                  }}
                />
              )}
            </FormRow>
          )}
        </div>
      );
      break;
    }
    case "when":
      body = (
        <FormRow label={t("rule.when.label")} hint={t("rule.when.hint")}>
          {(id) => (
            <SelectInput
              id={id}
              ariaLabel={t("rule.when.label")}
              value={whenChoice(value)}
              disabled={disabled}
              testId="pf-rule-when"
              options={WHEN_CHOICES.map((choice) => {
                const [person = "", role] = choice.split(":");
                return {
                  value: choice,
                  label:
                    choice === "always"
                      ? t("rule.when.always")
                      : t(`rule.when.${role ?? "any"}`, {
                          person: t(`rule.when.person.${person}`),
                        }),
                };
              })}
              onChange={(next) => {
                onChange(whenValue(next));
              }}
            />
          )}
        </FormRow>
      );
      break;
    case "checks": {
      const chosen = asStrings(value);
      const pool =
        shape.list === "disabled"
          ? context.checkRules
          : context.checkCategories;
      const options = [...new Set([...pool, ...chosen])];
      body = (
        <ChipToggles
          label={t(`rule.checks.${shape.list}`)}
          hint={t("rule.checks.hint")}
          options={options.map((v) => ({
            value: v,
            label:
              shape.list === "categories"
                ? t(`rule.checks.category.${v}`, { defaultValue: v })
                : v,
          }))}
          value={chosen}
          disabled={disabled}
          testId="pf-rule-checks"
          onChange={(next) => {
            if (next.length === 0) onChange({ type: "remove" });
            else set(next);
          }}
        />
      );
      break;
    }
    case "route":
      body = <p className="pf-hint">{t("rule.route")}</p>;
      break;
  }
  return (
    <div className="pf-rule" data-pf-at={pointer} data-testid={testId}>
      {body}
    </div>
  );
};
