import { useId, type ReactNode } from "react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { Input, Textarea } from "@shared/ui";
import { LANGS } from "../lib/submission";

// Мелкие поля формы точек сдачи: галочка с подписью и пара полей ru и en (5.0: пустой
// перевод подсвечивается).

export const Check = ({
  label,
  checked,
  onChange,
  disabled = false,
  title,
  testId,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  title?: string | undefined;
  testId?: string | undefined;
}) => {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className={clsx("psf-check", disabled && "psf-check-off")}
      title={title}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => {
          onChange(e.target.checked);
        }}
        data-testid={testId}
      />
      <span>{label}</span>
    </label>
  );
};

/**
 * Строка интерфейса парой ru и en. Пустой перевод при заполненном другом языке
 * подсвечивается подсказкой; `counter` показывает длину (подсказка срока до 200 знаков).
 */
export const LocalizedFields = ({
  label,
  value,
  onChange,
  disabled = false,
  multiline = false,
  max,
  issues,
  testId,
}: {
  label: string;
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  disabled?: boolean;
  multiline?: boolean;
  max?: number | undefined;
  /** Своя подсказка по языку (подсказка срока: длина, дата); иначе только пустой перевод. */
  issues?: Partial<Record<(typeof LANGS)[number], string | null>> | undefined;
  testId?: string | undefined;
}) => {
  const { t } = useTranslation("packStudio");
  const filled = LANGS.some((lang) => (value[lang] ?? "").trim() !== "");
  return (
    <fieldset className="psf-localized" data-testid={testId}>
      <legend>{label}</legend>
      {LANGS.map((lang) => {
        const text = value[lang] ?? "";
        const own = issues?.[lang] ?? null;
        const missing = filled && text.trim() === "";
        const hint =
          own ?? (missing ? t("submission.missingTranslation") : null);
        const counter =
          max !== undefined
            ? `${String(text.trim().length)}/${String(max)}`
            : null;
        const common = {
          value: text,
          disabled,
          "aria-label": `${label} (${lang})`,
          "data-testid": testId ? `${testId}-${lang}` : undefined,
        };
        return (
          <div className="psf-localized-row" key={lang}>
            <span className="psf-lang mono">{lang}</span>
            <div className="psf-localized-input">
              {multiline ? (
                <Textarea
                  {...common}
                  rows={2}
                  onChange={(e) => {
                    onChange({ ...value, [lang]: e.target.value });
                  }}
                />
              ) : (
                <Input
                  {...common}
                  onChange={(e) => {
                    onChange({ ...value, [lang]: e.target.value });
                  }}
                />
              )}
              {(hint !== null || counter !== null) && (
                <p className={clsx("hint", hint && "psf-warn")}>
                  {[hint, counter].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </fieldset>
  );
};

/** Заголовок блока карточки с действиями справа. */
export const BlockHead = ({
  title,
  hint,
  actions,
}: {
  title: string;
  hint?: string | undefined;
  actions?: ReactNode;
}) => (
  <div className="psf-block-head">
    <div className="psf-block-title">
      <h4>{title}</h4>
      {hint && <p className="hint">{hint}</p>}
    </div>
    {actions && <div className="psf-actions">{actions}</div>}
  </div>
);
