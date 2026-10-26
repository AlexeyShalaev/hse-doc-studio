import type { ReactNode } from "react";

export type ConfirmCheckProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
  /** Для проверки в тестах и для якоря поиска. */
  testId?: string;
};

// Флажок «я проверил(а)»: крупная область нажатия, подпись справа.
export const ConfirmCheck = ({
  checked,
  onChange,
  children,
  disabled = false,
  testId,
}: ConfirmCheckProps) => (
  <label
    className="flex items-start"
    style={{
      gap: 9,
      fontSize: 12.5,
      lineHeight: 1.45,
      cursor: disabled ? "default" : "pointer",
      color: "var(--fg-0)",
    }}
  >
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      data-testid={testId}
      onChange={(event) => {
        onChange(event.target.checked);
      }}
      style={{ marginTop: 2, accentColor: "var(--accent)", flexShrink: 0 }}
    />
    <span>{children}</span>
  </label>
);
