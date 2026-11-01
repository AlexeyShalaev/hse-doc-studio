import { clsx } from "clsx";

// Выключатель для строк настроек: настоящая кнопка с ролью switch, работает с
// клавиатуры, подпись берёт из <label htmlFor> строки или из aria-label.

export type SwitchProps = {
  checked: boolean;
  onChange: (next: boolean) => void;
  id?: string | undefined;
  disabled?: boolean | undefined;
  /** Подпись, когда рядом нет <label htmlFor>. */
  label?: string | undefined;
  describedBy?: string | undefined;
  testId?: string | undefined;
};

export const Switch = ({
  checked,
  onChange,
  id,
  disabled = false,
  label,
  describedBy,
  testId,
}: SwitchProps) => (
  <button
    type="button"
    role="switch"
    id={id}
    aria-checked={checked}
    aria-label={label}
    aria-describedby={describedBy}
    className={clsx("toggle adm-switch", checked && "on")}
    disabled={disabled}
    data-testid={testId}
    onClick={() => {
      onChange(!checked);
    }}
  />
);

Switch.displayName = "Switch";
