import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

export type PasswordFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Текст-подсказка под полем, пока нет ошибки. */
  hint?: string;
  error?: string | null;
  disabled?: boolean;
  autoFocus?: boolean;
  testId?: string;
};

// Поле пароля с кнопкой «показать». Менеджеры паролей не подставляют сюда
// ничего своего: пароль файла не пароль от аккаунта.
export const PasswordField = ({
  label,
  value,
  onChange,
  hint,
  error = null,
  disabled = false,
  autoFocus = false,
  testId,
}: PasswordFieldProps) => {
  const { t } = useTranslation("gitExchange");
  const uid = useId();
  const [shown, setShown] = useState(false);
  const inputId = `${uid}-input`;
  const noteId = `${uid}-note`;
  const note = error ?? hint ?? null;

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      <div className="flex" style={{ gap: 6 }}>
        <input
          id={inputId}
          type={shown ? "text" : "password"}
          className="input"
          style={{ flex: 1, minWidth: 0 }}
          value={value}
          disabled={disabled}
          autoComplete="off"
          spellCheck={false}
          autoFocus={autoFocus}
          data-testid={testId}
          aria-invalid={error !== null}
          aria-describedby={note ? noteId : undefined}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
        <button
          type="button"
          className="btn"
          aria-pressed={shown}
          aria-label={shown ? t("password.hide") : t("password.show")}
          title={shown ? t("password.hide") : t("password.show")}
          onClick={() => {
            setShown((current) => !current);
          }}
        >
          {shown ? (
            <EyeOff size={14} aria-hidden="true" />
          ) : (
            <Eye size={14} aria-hidden="true" />
          )}
        </button>
      </div>
      {note && (
        <p
          id={noteId}
          className={error ? "text-xs" : "hint"}
          role={error ? "alert" : undefined}
          style={{ margin: 0, ...(error ? { color: "var(--c-err)" } : {}) }}
        >
          {note}
        </p>
      )}
    </div>
  );
};
