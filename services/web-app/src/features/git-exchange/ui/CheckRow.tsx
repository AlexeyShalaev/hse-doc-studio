import type { ReactNode } from "react";

export type CheckRowProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
  testId?: string;
};

// Флажок с подписью справа: вся строка нажимается, пояснение идёт под подписью.
export const CheckRow = ({
  checked,
  onChange,
  children,
  hint,
  disabled = false,
  testId,
}: CheckRowProps) => (
  <label
    className="flex items-start"
    style={{
      gap: "0.5625rem",
      fontSize: "0.78125rem",
      lineHeight: 1.45,
      cursor: disabled ? "default" : "pointer",
      opacity: disabled ? 0.6 : 1,
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
      style={{
        marginTop: "0.125rem",
        accentColor: "var(--accent)",
        flexShrink: 0,
      }}
    />
    <span style={{ minWidth: 0 }}>
      {children}
      {hint && (
        <span
          className="dim"
          style={{
            display: "block",
            fontSize: "0.6875rem",
            marginTop: "0.125rem",
          }}
        >
          {hint}
        </span>
      )}
    </span>
  </label>
);
