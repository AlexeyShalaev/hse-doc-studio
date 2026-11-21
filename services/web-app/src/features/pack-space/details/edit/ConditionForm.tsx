import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { RuleChange, RuleFormContext } from "@features/pack-forms/rule";
import {
  WHEN_CHOICES,
  listOptions,
  selectedOf,
  siblingFields,
  whenChoice,
  whenValue,
} from "@features/pack-forms/lib/ruleRecord";
import { asRecord, asString, asStrings } from "@features/pack-forms/lib/raw";
import { soft, type Words } from "../words";
import type { EditTarget } from "./useConditionEdit";

// Мини-формы условий по месту: те же записи описания версии, что в «Содержимом», но подписаны
// фразой («Документ нужен, когда вид работы:») и с чипами-флажками вместо выпадающих списков.
// Форма ничего не решает: показывает значение записи и отдаёт новое, что оно меняет, считает
// сервер.

export type ConditionFormProps = {
  target: EditTarget;
  /** Текущее значение записи; `undefined`, если ключа в описании нет. */
  value: unknown;
  context: RuleFormContext;
  disabled: boolean;
  words: Words;
  /** Названия полей анкеты и правил проверки по их id: подписи чипов и списков. */
  names: ReadonlyMap<string, string>;
  onChange: (change: RuleChange) => void;
};

/** К какому условию студента относится список: подписи значений берутся у него. */
const LIST_SUBJECT = {
  kinds: "kind",
  staffing: "staffing",
  langs: "lang",
} as const;

const set = (value: unknown): RuleChange => ({ type: "set", value });
const REMOVE: RuleChange = { type: "remove" };

type ChipsProps = {
  legend: string;
  hint?: string;
  options: readonly { value: string; label: string }[];
  value: readonly string[];
  disabled: boolean;
  testId: string;
  onChange: (next: string[]) => void;
};

/** Чипы-флажки: нажатый чип включён, подпись фразой стоит над ними. */
const Chips = ({
  legend,
  hint,
  options,
  value,
  disabled,
  testId,
  onChange,
}: ChipsProps) => (
  <fieldset className="sp-cond" data-testid={testId}>
    <legend className="sp-cond-legend">{legend}</legend>
    <div className="sp-chips">
      {options.map((option) => (
        <label key={option.value} className="sp-chip">
          <input
            type="checkbox"
            checked={value.includes(option.value)}
            disabled={disabled}
            onChange={() => {
              const on = value.includes(option.value);
              onChange(
                options
                  .map((o) => o.value)
                  .filter((v) =>
                    v === option.value ? !on : value.includes(v),
                  ),
              );
            }}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </div>
    {hint ? <p className="sp-cond-hint">{hint}</p> : null}
  </fieldset>
);

/** Поле текста, которое записывается, когда человек закончил (уход из поля или Enter). */
const CommitText = ({
  label,
  value,
  disabled,
  testId,
  onCommit,
}: {
  label: string;
  value: string;
  disabled: boolean;
  testId: string;
  onCommit: (text: string) => void;
}) => {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    setDraft(value);
  }
  const done = () => {
    if (draft !== value) onCommit(draft);
  };
  return (
    <div className="sp-cond">
      <label className="sp-cond-legend" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="input sp-cond-input"
        value={draft}
        disabled={disabled}
        data-testid={testId}
        onChange={(event) => {
          setDraft(event.target.value);
        }}
        onBlur={done}
        onKeyDown={(event) => {
          if (event.key === "Enter") done();
        }}
      />
    </div>
  );
};

const scalar = (value: unknown): string =>
  typeof value === "string" ||
  typeof value === "number" ||
  typeof value === "boolean"
    ? String(value)
    : "";

export const ConditionForm = ({
  target,
  value,
  context,
  disabled,
  words,
  names,
  onChange,
}: ConditionFormProps) => {
  const { t } = useTranslation("packSpace");
  const { shape, kind, pointer } = target;
  const selectId = useId();
  switch (shape.kind) {
    case "list": {
      const all = listOptions(shape.list, context.manifest);
      const subject = LIST_SUBJECT[shape.list];
      return (
        <Chips
          legend={t(`details.edit.phrase.${kind}`, {
            defaultValue: t("details.edit.phrase.other"),
          })}
          hint={t("details.edit.hintList")}
          options={all.map((v) => ({
            value: v,
            label: words.value(subject, v),
          }))}
          value={selectedOf(value, all)}
          disabled={disabled}
          testId="sp-cond-list"
          onChange={(next) => {
            // Всё выбрано или ничего: ограничения нет, ключ убирается.
            onChange(
              next.length === 0 || next.length === all.length
                ? REMOVE
                : set(next),
            );
          }}
        />
      );
    }
    case "flag":
      return (
        <label className="sp-cond sp-flag">
          <input
            type="checkbox"
            checked={value === true}
            disabled={disabled}
            data-testid="sp-cond-flag"
            onChange={(event) => {
              onChange(event.target.checked ? set(true) : REMOVE);
            }}
          />
          <span>{t(`details.edit.flag.${shape.flag}`)}</span>
        </label>
      );
    case "visibleIf": {
      const visible = asRecord(value);
      const field = asString(visible.field);
      const others = siblingFields(context.manifest, pointer);
      const name = (id: string) => names.get(id) ?? id;
      return (
        <div className="sp-cond">
          <label className="sp-cond-legend" htmlFor={selectId}>
            {t("details.edit.phrase.visible_if")}
          </label>
          <select
            id={selectId}
            className="input sp-cond-input"
            value={field}
            disabled={disabled}
            data-testid="sp-cond-visible-field"
            onChange={(event) => {
              const next = event.target.value;
              onChange(
                next
                  ? set({ field: next, equals: visible.equals ?? true })
                  : REMOVE,
              );
            }}
          >
            <option value="">{t("details.edit.always")}</option>
            {field !== "" && !others.includes(field) ? (
              <option value={field}>{name(field)}</option>
            ) : null}
            {others.map((id) => (
              <option key={id} value={id}>
                {t("details.edit.whenField", { field: name(id) })}
              </option>
            ))}
          </select>
          {field !== "" && (
            <CommitText
              label={t("details.edit.equals")}
              value={scalar(visible.equals)}
              disabled={disabled}
              testId="sp-cond-visible-equals"
              onCommit={(text) => {
                onChange(
                  set({
                    field,
                    equals:
                      text === "true" ? true : text === "false" ? false : text,
                  }),
                );
              }}
            />
          )}
        </div>
      );
    }
    case "when":
      return (
        <div className="sp-cond">
          <label className="sp-cond-legend" htmlFor={selectId}>
            {t("details.edit.phrase.slot_when")}
          </label>
          <select
            id={selectId}
            className="input sp-cond-input"
            value={whenChoice(value)}
            disabled={disabled}
            data-testid="sp-cond-when"
            onChange={(event) => {
              onChange(whenValue(event.target.value));
            }}
          >
            {WHEN_CHOICES.map((choice) => {
              const [person = "", role] = choice.split(":");
              return (
                <option key={choice} value={choice}>
                  {choice === "always"
                    ? t("details.edit.always")
                    : t(`details.edit.when.${role ?? "any"}`, {
                        person: soft(words.subject(person)),
                      })}
                </option>
              );
            })}
          </select>
        </div>
      );
    case "checks": {
      const chosen = asStrings(value);
      const pool =
        shape.list === "disabled"
          ? context.checkRules
          : context.checkCategories;
      const options = [...new Set([...pool, ...chosen])];
      return (
        <Chips
          legend={t(`details.edit.phrase.checks_${shape.list}`)}
          hint={t("details.edit.hintChecks")}
          options={options.map((v) => ({ value: v, label: names.get(v) ?? v }))}
          value={chosen}
          disabled={disabled}
          testId="sp-cond-checks"
          onChange={(next) => {
            onChange(next.length === 0 ? REMOVE : set(next));
          }}
        />
      );
    }
    case "route":
      return null;
  }
};
