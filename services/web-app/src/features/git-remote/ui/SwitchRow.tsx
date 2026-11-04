import type { ReactNode } from "react";
import { clsx } from "clsx";
import { Spinner } from "@shared/ui/Spinner";

export type SwitchRowProps = {
  id: string;
  label: string;
  hint?: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  /** Запрос уже идёт: рядом с выключателем крутится индикатор. */
  busy?: boolean;
};

// Строка «название, пояснение, выключатель». Выключатель настоящая кнопка с
// ролью switch: работает с клавиатуры и называется скринридером.
export const SwitchRow = ({
  id,
  label,
  hint,
  checked,
  onChange,
  disabled = false,
  busy = false,
}: SwitchRowProps) => (
  <div
    className="flex items-center justify-between"
    style={{
      padding: "0.75rem",
      background: "var(--bg-2)",
      borderRadius: "var(--r-2)",
      gap: "0.75rem",
    }}
  >
    <div className="flex flex-col" style={{ gap: "0.125rem", minWidth: 0 }}>
      <strong id={`${id}-label`} style={{ fontSize: "0.78125rem" }}>
        {label}
      </strong>
      {hint && (
        <span
          id={`${id}-hint`}
          className="dim"
          style={{ fontSize: "0.6875rem", lineHeight: 1.5 }}
        >
          {hint}
        </span>
      )}
    </div>
    <div className="flex items-center" style={{ gap: "0.5rem", flexShrink: 0 }}>
      {busy && <Spinner size="sm" />}
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        {...(hint ? { "aria-describedby": `${id}-hint` } : {})}
        className={clsx("toggle", checked && "on")}
        disabled={disabled}
        style={disabled ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
        onClick={() => {
          onChange(!checked);
        }}
      />
    </div>
  </div>
);
