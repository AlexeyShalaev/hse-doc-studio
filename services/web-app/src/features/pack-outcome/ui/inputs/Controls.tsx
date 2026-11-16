import { useRef, type KeyboardEvent } from "react";
import { Select } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";

export type ControlOption = { value: string; label: string };

type CommonProps = {
  /** Идентификатор подписи вводной (aria-labelledby). */
  labelledBy: string;
  describedBy: string;
  testId: string;
};

/** Больше четырёх значений: выпадающий список, как в дизайне (раздел 3.3). */
export const SELECT_FROM = 5;

type BoolProps = CommonProps & {
  checked: boolean;
  /** Подпись состояния рядом с переключателем. */
  stateLabel: string;
  name: string;
  onChange: (next: boolean) => void;
};

/** Булева вводная: переключатель с подписью состояния («Да» и «Нет»). */
export const ToggleControl = ({
  checked,
  stateLabel,
  name,
  onChange,
  describedBy,
  testId,
}: BoolProps) => (
  <span className="po-in-toggle">
    <Switch
      checked={checked}
      onChange={onChange}
      label={name}
      describedBy={describedBy}
      testId={testId}
    />
    <span className="po-in-state" aria-hidden="true">
      {stateLabel}
    </span>
  </span>
);

type RadioProps = CommonProps & {
  options: ControlOption[];
  value: string;
  onChange: (next: string) => void;
};

/**
 * Выбор из нескольких значений (до четырёх): группа радиокнопок с одной точкой входа в порядок
 * Tab. Стрелки, Home и End переходят и сразу выбирают, как у стандартной группы радио.
 */
export const RadioControl = ({
  options,
  value,
  onChange,
  labelledBy,
  describedBy,
  testId,
}: RadioProps) => {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const checkedAt = options.findIndex((option) => option.value === value);
  const entry = checkedAt === -1 ? 0 : checkedAt;

  const move = (to: number) => {
    const next = options[(to + options.length) % options.length];
    if (!next) return;
    onChange(next.value);
    refs.current[(to + options.length) % options.length]?.focus();
  };
  const onKeyDown = (event: KeyboardEvent, at: number) => {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      move(at + 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      move(at - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      move(0);
    } else if (event.key === "End") {
      event.preventDefault();
      move(options.length - 1);
    }
  };

  return (
    <div
      role="radiogroup"
      className="po-in-radio"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      data-testid={testId}
    >
      {options.map((option, at) => (
        <button
          key={option.value}
          ref={(node) => {
            refs.current[at] = node;
          }}
          type="button"
          role="radio"
          className="po-in-option"
          aria-checked={option.value === value}
          tabIndex={at === entry ? 0 : -1}
          data-testid={`${testId}-${option.value}`}
          onClick={() => {
            onChange(option.value);
          }}
          onKeyDown={(event) => {
            onKeyDown(event, at);
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};

type DropdownProps = CommonProps & {
  options: ControlOption[];
  value: string;
  name: string;
  onChange: (next: string) => void;
};

/** Длинный список значений: выпадающий список с подписью вводной. */
export const DropdownControl = ({
  options,
  value,
  name,
  onChange,
  testId,
}: DropdownProps) => (
  <Select
    id={testId}
    ariaLabel={name}
    className="po-in-select"
    value={value}
    options={options}
    onValueChange={onChange}
  />
);
