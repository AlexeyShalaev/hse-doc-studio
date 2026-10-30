import { forwardRef, useId } from "react";
import { clsx } from "clsx";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "../Tooltip";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
  id?: string;
  hint?: string;
  isMono?: boolean;
  /**
   * Значение задано окружением сервера: поле только для чтения, приглушено,
   * внутри замок с подсказкой. Строка заменяет стандартный текст подсказки.
   */
  locked?: boolean | string | undefined;
};

/** Замок внутри закрытого поля: подсказка объясняет, где меняется значение. */
const LockMark = ({ text }: { text: string | true }) => {
  const { t } = useTranslation("uiPrimitives");
  const content = text === true ? t("adminKit.lockedHint") : text;
  return (
    <Tooltip content={content}>
      <span
        className="input-lock"
        tabIndex={0}
        role="img"
        aria-label={content}
        data-testid="input-locked"
      >
        <Lock size={13} aria-hidden="true" />
      </span>
    </Tooltip>
  );
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, hint, isMono, locked, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
    const uid = useId();
    const errorId = `${uid}-error`;
    const hintId = `${uid}-hint`;
    // Ошибка и подсказка связаны с полем: скринридер читает их вместе с меткой.
    const describedBy =
      [props["aria-describedby"], error ? errorId : hint ? hintId : undefined]
        .filter(Boolean)
        .join(" ") || undefined;
    const control = (
      <input
        ref={ref}
        id={inputId}
        className={clsx(
          "input",
          isMono && "mono",
          error && "!border-c-err",
          className,
        )}
        {...props}
        readOnly={locked ? true : props.readOnly}
        data-locked={locked ? "true" : undefined}
        aria-invalid={error ? true : props["aria-invalid"]}
        aria-describedby={describedBy}
      />
    );
    return (
      <div className="field">
        {label && <label htmlFor={inputId}>{label}</label>}
        {locked ? (
          <span className="input-locked-wrap">
            {control}
            <LockMark text={locked} />
          </span>
        ) : (
          control
        )}
        {error && (
          <p id={errorId} className="text-xs text-c-err" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={hintId} className="hint">
            {hint}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";
