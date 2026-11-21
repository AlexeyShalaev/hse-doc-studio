import type { OutcomeInput } from "@entities/pack-studio";
import { Select } from "@shared/ui";
import { useSituationLabels } from "./useSituationLabels";

/** До скольких значений показываем сегменты в ряд. */
const SEGMENTS_UP_TO = 3;

type ValuePickerProps = {
  input: OutcomeInput;
  value: string;
  onPick: (value: string) => void;
  /** `popover`: длинный список вертикально; `row`: длинный список выпадающим выбором. */
  variant: "popover" | "row";
};

/**
 * Выбор значения условия: 2-3 значения сегментами, больше списком (pack-studio-ux.md, 5.3).
 * Значение из адреса, которого нет в версии, остаётся видимым.
 */
export const ValuePicker = ({
  input,
  value,
  onPick,
  variant,
}: ValuePickerProps) => {
  const { inputLabel, valueLabel } = useSituationLabels();
  const name = inputLabel(input);
  const options = input.values.map((item) => ({
    value: item.value,
    label: valueLabel(input, item.value),
  }));
  if (!options.some((option) => option.value === value)) {
    options.push({ value, label: valueLabel(input, value) });
  }
  if (options.length > SEGMENTS_UP_TO && variant === "row") {
    return (
      <Select
        id={`sp-sit-${input.id}`}
        ariaLabel={name}
        className="sp-sit-select"
        value={value}
        options={options}
        onValueChange={onPick}
      />
    );
  }
  return (
    <div
      role="radiogroup"
      aria-label={name}
      className={
        options.length > SEGMENTS_UP_TO ? "sp-sit-list" : "sp-sit-segments"
      }
      data-testid={`sp-sit-picker-${input.id}`}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          className="sp-sit-option"
          aria-checked={option.value === value}
          data-testid={`sp-sit-value-${input.id}-${option.value}`}
          onClick={() => {
            onPick(option.value);
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};
