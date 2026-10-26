export type SegmentedOption<V extends string> = {
  value: V;
  label: string;
};

export type SegmentedProps<V extends string> = {
  options: SegmentedOption<V>[];
  value: V;
  onChange: (value: V) => void;
  /** Имя группы для скринридера. */
  label: string;
  disabled?: boolean;
};

// Переключатель на два-три значения: радио-группа в виде кнопок.
export const Segmented = <V extends string>({
  options,
  value,
  onChange,
  label,
  disabled = false,
}: SegmentedProps<V>) => (
  <div
    role="radiogroup"
    aria-label={label}
    className="flex"
    style={{
      gap: 2,
      padding: 2,
      borderRadius: "var(--r-2)",
      background: "var(--bg-2)",
      border: "1px solid var(--border)",
    }}
  >
    {options.map((option) => {
      const active = option.value === value;
      return (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={active}
          disabled={disabled}
          className={active ? "btn xs primary" : "btn xs ghost"}
          style={{ flex: 1, justifyContent: "center" }}
          onClick={() => {
            onChange(option.value);
          }}
        >
          {option.label}
        </button>
      );
    })}
  </div>
);
