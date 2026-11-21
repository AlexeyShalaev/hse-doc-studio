import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import type { SituationModel } from "./useSituationModel";
import { useSituationLabels } from "./useSituationLabels";
import { useAffectsText } from "./useAffectsText";
import { ValuePicker } from "./ValuePicker";

/**
 * Условие кнопкой: «Работа: Проектная». Нажатие открывает маленькое окно со значениями и строкой
 * «Что это меняет»; выбор записывается сразу и закрывает окно (два клика). Изменённое условие
 * с акцентной рамкой.
 */
export const InputChip = ({
  input,
  model,
}: {
  input: OutcomeInput;
  model: SituationModel;
}) => {
  const { t } = useTranslation("packSpace");
  const { inputLabel, valueLabel } = useSituationLabels();
  const affects = useAffectsText();
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const value = model.valueOf(input);
  const base = model.baseOf(input);
  const changed = value !== base;
  const name = inputLabel(input);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="sp-chip"
          data-changed={changed ? "true" : undefined}
          data-testid={`sp-sit-chip-${input.id}`}
        >
          <span className="sp-chip-k">{name}</span>{" "}
          <span className="sp-chip-v">{valueLabel(input, value)}</span>
          <ChevronDown size="0.75rem" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent width={300} align="start" aria-labelledby={titleId}>
        <div className="sp-sit-pop">
          <h3 className="sp-sit-pop-title" id={titleId}>
            {name}
          </h3>
          <ValuePicker
            input={input}
            value={value}
            variant="popover"
            onPick={(next) => {
              if (next !== value) model.setInput(input, next);
              setOpen(false);
            }}
          />
          <p className="sp-sit-pop-note" data-testid="sp-sit-affects">
            {affects(input)}
          </p>
          {changed ? (
            <button
              type="button"
              className="sp-link"
              data-testid="sp-sit-restore"
              onClick={() => {
                model.setInput(input, base);
                setOpen(false);
              }}
            >
              {t("situation.restore", { value: valueLabel(input, base) })}
            </button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
};
