import { memo, useId } from "react";
import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeElementRef, OutcomeInput } from "@entities/pack-studio";
import {
  DropdownControl,
  RadioControl,
  SELECT_FROM,
  ToggleControl,
  type ControlOption,
} from "./Controls";
import { useInputLabels } from "./useLabels";

/** Сколько связанных элементов показываем списком; остальные одной строкой «и ещё N». */
const LINKS_SHOWN = 8;

type InputRowProps = {
  input: OutcomeInput;
  /** Значение, которое показывает контрол (черновик или адрес). */
  value: string;
  /** Исходное значение: сценарий либо умолчание версии. */
  base: string;
  /** Сценарий задаёт значение, отличное от умолчания версии. */
  fromScenario: boolean;
  /** Вводная не меняет разделы результата (блок «Не влияют»). */
  inert: boolean;
  /** Связанные элементы результата из трассы; пусто, если связей нет. */
  linked: OutcomeElementRef[];
  highlighted: boolean;
  onChange: (id: string, value: string) => void;
  onReset: (id: string) => void;
  onHighlight: (id: string | null) => void;
  onSelect: (element: OutcomeElementRef) => void;
};

/**
 * Одна вводная: подпись, контрол по типу, «Сбросить», пояснение «Влияет на» (или почему не
 * влияет) и подсветка связанных элементов результата. Строки не перерисовываются, пока их
 * значения не менялись, поэтому выбор в одной вводной не трогает остальные.
 */
export const InputRow = memo(
  ({
    input,
    value,
    base,
    fromScenario,
    inert,
    linked,
    highlighted,
    onChange,
    onReset,
    onHighlight,
    onSelect,
  }: InputRowProps) => {
    const { t } = useTranslation("packOutcome");
    const { inputLabel, valueLabel } = useInputLabels();
    const uid = useId();
    const labelId = `${uid}-label`;
    const hintId = `${uid}-hint`;
    const name = inputLabel(input);
    const changed = value !== base;
    const testId = `outcome-input-${input.id}`;

    const options: ControlOption[] = input.values.map((item) => ({
      value: item.value,
      label: valueLabel(input, item.value),
    }));
    // Значение из адреса, которого нет в словаре версии, остаётся видимым: его не прячем.
    if (!options.some((option) => option.value === value)) {
      options.push({ value, label: valueLabel(input, value) });
    }

    const sections = input.affects.map((id) => t(`sections.${id}`)).join(", ");
    const hint = inert
      ? input.rules === 0
        ? t("inputs.inert.none")
        : t("inputs.inert.minor", { count: input.rules })
      : [
          t("inputs.affects", { sections }),
          input.rules > 0 ? t("inputs.readers", { count: input.rules }) : "",
        ]
          .filter((part) => part !== "")
          .join(". ");

    const common = {
      labelledBy: labelId,
      describedBy: hintId,
      testId: `outcome-control-${input.id}`,
    };

    let control;
    if (input.type === "bool") {
      control = (
        <ToggleControl
          {...common}
          name={name}
          checked={value === "yes"}
          stateLabel={valueLabel(input, value)}
          onChange={(next) => {
            onChange(input.id, next ? "yes" : "no");
          }}
        />
      );
    } else if (options.length >= SELECT_FROM) {
      control = (
        <DropdownControl
          {...common}
          name={name}
          options={options}
          value={value}
          onChange={(next) => {
            onChange(input.id, next);
          }}
        />
      );
    } else {
      control = (
        <RadioControl
          {...common}
          options={options}
          value={value}
          onChange={(next) => {
            onChange(input.id, next);
          }}
        />
      );
    }

    return (
      <div
        className="po-in-row"
        role="group"
        aria-labelledby={labelId}
        data-changed={changed ? "true" : undefined}
        data-inert={inert ? "true" : undefined}
        data-highlighted={highlighted ? "true" : undefined}
        data-testid={testId}
      >
        <div className="po-in-head">
          <span className="po-in-label" id={labelId}>
            {name}
          </span>
          {changed && (
            <span className="po-in-mark" data-testid={`${testId}-changed`}>
              {t("inputs.changedMark")}
            </span>
          )}
          {!changed && fromScenario && (
            <span className="po-in-mark" data-kind="scenario">
              {t("inputs.fromScenario")}
            </span>
          )}
          <button
            type="button"
            className="icon-btn sm"
            disabled={!changed}
            aria-label={t("inputs.resetOne", { name })}
            title={t("inputs.resetOne", { name })}
            data-testid={`${testId}-reset`}
            onClick={() => {
              onReset(input.id);
            }}
          >
            <RotateCcw size="0.8125rem" aria-hidden="true" />
          </button>
        </div>
        {control}
        <div className="po-in-foot">
          <p className="po-in-hint" id={hintId}>
            {hint}
          </p>
          <span className="po-in-actions">
            {linked.length > 0 && (
              <button
                type="button"
                className="po-link"
                aria-pressed={highlighted}
                data-testid={`${testId}-highlight`}
                onClick={() => {
                  onHighlight(highlighted ? null : input.id);
                }}
              >
                {t(highlighted ? "inputs.links.hide" : "inputs.links.show", {
                  count: linked.length,
                })}
              </button>
            )}
          </span>
        </div>
        {highlighted && linked.length > 0 && (
          <ul
            className="po-in-links"
            aria-label={t("inputs.links.title", { name })}
            data-testid={`${testId}-links`}
          >
            {linked.slice(0, LINKS_SHOWN).map((element) => (
              <li key={`${element.section}:${element.id}`}>
                <button
                  type="button"
                  className="po-link"
                  onClick={() => {
                    onSelect(element);
                  }}
                >
                  {t(`sections.${element.section}`)}: {element.id}
                </button>
              </li>
            ))}
            {linked.length > LINKS_SHOWN && (
              <li className="po-in-more">
                {t("inputs.links.more", { count: linked.length - LINKS_SHOWN })}
              </li>
            )}
          </ul>
        )}
      </div>
    );
  },
);
InputRow.displayName = "InputRow";
