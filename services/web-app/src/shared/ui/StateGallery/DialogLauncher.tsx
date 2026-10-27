import { useState, type ReactNode } from "react";

export type DialogLauncherProps = {
  /** Что написано на кнопке: «Открыть окно». */
  label: string;
  /** Окно получает, открыто ли оно, и функцию закрытия. */
  children: (state: { isOpen: boolean; close: () => void }) => ReactNode;
  /** Дополнительные кнопки и пояснение рядом. */
  hint?: ReactNode;
  /** Открыть окно сразу: так делают живые записи, где «Открыть» уже нажато. */
  defaultOpen?: boolean;
};

/**
 * Кнопка, которая открывает окно поверх галереи. Окна не лежат на странице
 * сами по себе, поэтому в галерее каждое показано по нажатию.
 */
export const DialogLauncher = ({
  label,
  children,
  hint,
  defaultOpen = false,
}: DialogLauncherProps) => {
  const [isOpen, setOpen] = useState(defaultOpen);
  return (
    <div className="flex items-center flex-wrap" style={{ gap: 12 }}>
      <button
        type="button"
        className="btn"
        onClick={() => {
          setOpen(true);
        }}
      >
        {label}
      </button>
      {hint && (
        <span className="dim" style={{ fontSize: 12 }}>
          {hint}
        </span>
      )}
      {children({
        isOpen,
        close: () => {
          setOpen(false);
        },
      })}
    </div>
  );
};
