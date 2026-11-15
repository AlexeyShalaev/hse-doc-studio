import { useId, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { UI_LANGS, asLocalized, type Localized } from "../lib/raw";

// Общий каркас форм Студии шаблонов (template-studio.md, 5.0): поля пишут
// значение по окончании правки (уход фокуса, Enter, выбор в списке), а не на
// каждую букву: каждая запись это точечная правка YAML на диске.

type CommitInputProps = {
  value: string;
  onCommit: (next: string) => void;
  ariaLabel: string;
  placeholder?: string | undefined;
  mono?: boolean | undefined;
  disabled?: boolean | undefined;
  multiline?: boolean | undefined;
  invalid?: boolean | undefined;
  id?: string | undefined;
  testId?: string | undefined;
  list?: string | undefined;
};

/** Текстовое поле с записью по уходу фокуса или Enter; Escape возвращает значение. */
export const CommitInput = ({
  value,
  onCommit,
  ariaLabel,
  placeholder,
  mono,
  disabled,
  multiline,
  invalid,
  id,
  testId,
  list,
}: CommitInputProps) => {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);
  // Значение с сервера (после записи или чужой правки) заменяет черновик, пока поле не в правке.
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    if (!editing) setDraft(value);
  }
  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      setDraft(value);
    }
    if (event.key === "Enter" && !(multiline && event.shiftKey)) {
      if (multiline && !event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      commit();
    }
  };
  const shared = {
    id,
    "aria-label": ariaLabel,
    placeholder,
    disabled,
    value: draft,
    "aria-invalid": invalid === true ? true : undefined,
    "data-testid": testId,
    onFocus: () => {
      setEditing(true);
    },
    onBlur: commit,
    onKeyDown,
  };
  return multiline ? (
    <textarea
      {...shared}
      className={clsx("textarea pf-input", invalid && "pf-invalid")}
      rows={3}
      onChange={(e) => {
        setDraft(e.target.value);
      }}
    />
  ) : (
    <input
      {...shared}
      type="text"
      list={list}
      className={clsx(
        "input pf-input",
        mono && "mono",
        invalid && "pf-invalid",
      )}
      onChange={(e) => {
        setDraft(e.target.value);
      }}
    />
  );
};

type LocalizedInputProps = {
  label: string;
  value: unknown;
  onCommit: (next: Localized) => void;
  disabled?: boolean | undefined;
  multiline?: boolean | undefined;
  /** Подсвечивать пустой язык, даже если другой тоже пуст (обязательная подпись). */
  required?: boolean | undefined;
  testId?: string | undefined;
};

/** Подпись парой ru и en (5.0): пустой перевод подсвечен, если другой язык заполнен. */
export const LocalizedInput = ({
  label,
  value,
  onCommit,
  disabled,
  multiline,
  required,
  testId,
}: LocalizedInputProps) => {
  const { t } = useTranslation("packForms");
  const current = asLocalized(value);
  const anyFilled = UI_LANGS.some((lang) => Boolean(current[lang]));
  return (
    <fieldset className="pf-localized" data-testid={testId}>
      <legend className="pf-label">{label}</legend>
      {UI_LANGS.map((lang) => {
        const text = current[lang] ?? "";
        const missing = !text && (anyFilled || Boolean(required));
        return (
          <div key={lang} className="pf-lang-row">
            <span className="pf-lang mono" aria-hidden="true">
              {lang}
            </span>
            <CommitInput
              value={text}
              ariaLabel={`${label} (${lang})`}
              disabled={disabled}
              multiline={multiline}
              invalid={missing}
              placeholder={missing ? t("kit.missingLang") : undefined}
              testId={testId ? `${testId}-${lang}` : undefined}
              onCommit={(next) => {
                onCommit({ ...current, [lang]: next });
              }}
            />
          </div>
        );
      })}
    </fieldset>
  );
};

export type Choice = { value: string; label: string };

type SelectInputProps = {
  value: string;
  options: Choice[];
  onChange: (next: string) => void;
  ariaLabel: string;
  disabled?: boolean | undefined;
  testId?: string | undefined;
  id?: string | undefined;
};

/** Список выбора: запись сразу при выборе. Значение не из списка показано как есть. */
export const SelectInput = ({
  value,
  options,
  onChange,
  ariaLabel,
  disabled,
  testId,
  id,
}: SelectInputProps) => {
  const known = options.some((o) => o.value === value);
  return (
    <select
      id={id}
      className="input pf-input"
      value={value}
      aria-label={ariaLabel}
      disabled={disabled}
      data-testid={testId}
      onChange={(e) => {
        onChange(e.target.value);
      }}
    >
      {!known && <option value={value}>{value}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
};

type CheckInputProps = {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean | undefined;
  hint?: string | undefined;
  testId?: string | undefined;
};

export const CheckInput = ({
  label,
  checked,
  onChange,
  disabled,
  hint,
  testId,
}: CheckInputProps) => (
  <label className="pf-check">
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      data-testid={testId}
      onChange={(e) => {
        onChange(e.target.checked);
      }}
    />
    <span>
      {label}
      {hint && <span className="pf-hint">{hint}</span>}
    </span>
  </label>
);

type ChipTogglesProps = {
  label: string;
  options: Choice[];
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean | undefined;
  hint?: string | undefined;
  testId?: string | undefined;
};

/** Набор значений галочками (виды работы, состав, языки); порядок как у вариантов. */
export const ChipToggles = ({
  label,
  options,
  value,
  onChange,
  disabled,
  hint,
  testId,
}: ChipTogglesProps) => (
  <fieldset className="pf-chips" data-testid={testId}>
    <legend className="pf-label">{label}</legend>
    <div className="pf-chip-row">
      {options.map((option) => {
        const on = value.includes(option.value);
        return (
          <label key={option.value} className={clsx("pf-chip", on && "on")}>
            <input
              type="checkbox"
              checked={on}
              disabled={disabled}
              onChange={() => {
                onChange(
                  options
                    .map((o) => o.value)
                    .filter((v) =>
                      v === option.value ? !on : value.includes(v),
                    ),
                );
              }}
            />
            {option.label}
          </label>
        );
      })}
    </div>
    {hint && <p className="pf-hint">{hint}</p>}
  </fieldset>
);

type FormRowProps = {
  label: string;
  hint?: ReactNode | undefined;
  children: (id: string) => ReactNode;
};

/** Подпись, поле и подсказка под ним; поле получает id для подписи. */
export const FormRow = ({ label, hint, children }: FormRowProps) => {
  const id = useId();
  return (
    <div className="pf-row">
      <label className="pf-label" htmlFor={id}>
        {label}
      </label>
      {children(id)}
      {hint && <div className="pf-hint">{hint}</div>}
    </div>
  );
};

type OrderButtonsProps = {
  index: number;
  count: number;
  onMove: (to: number) => void;
  onDelete?: (() => void) | undefined;
  disabled?: boolean | undefined;
  deleteDisabledReason?: string | undefined;
  label: string;
};

/** Вверх, вниз и удалить у элемента списка (порядок в YAML равен порядку в интерфейсе). */
export const OrderButtons = ({
  index,
  count,
  onMove,
  onDelete,
  disabled,
  deleteDisabledReason,
  label,
}: OrderButtonsProps) => {
  const { t } = useTranslation("packForms");
  return (
    <span className="pf-order">
      <button
        type="button"
        className="icon-btn"
        disabled={disabled || index === 0}
        aria-label={t("kit.up", { name: label })}
        title={t("kit.up", { name: label })}
        onClick={() => {
          onMove(index - 1);
        }}
      >
        <ArrowUp size="0.75rem" />
      </button>
      <button
        type="button"
        className="icon-btn"
        disabled={disabled || index >= count - 1}
        aria-label={t("kit.down", { name: label })}
        title={t("kit.down", { name: label })}
        onClick={() => {
          onMove(index + 1);
        }}
      >
        <ArrowDown size="0.75rem" />
      </button>
      {onDelete && (
        <button
          type="button"
          className="icon-btn"
          disabled={disabled || Boolean(deleteDisabledReason)}
          aria-label={t("kit.delete", { name: label })}
          title={deleteDisabledReason ?? t("kit.delete", { name: label })}
          onClick={onDelete}
        >
          <Trash2 size="0.75rem" />
        </button>
      )}
    </span>
  );
};

/** Блок формы с заголовком и действиями справа. */
export const FormBlock = ({
  title,
  lead,
  actions,
  children,
  testId,
}: {
  title: string;
  lead?: string | undefined;
  actions?: ReactNode | undefined;
  children: ReactNode;
  testId?: string | undefined;
}) => (
  <section className="pf-block" data-testid={testId}>
    <header className="pf-block-head">
      <div className="pf-block-titles">
        <h3 className="pf-block-title">{title}</h3>
        {lead && <p className="pf-block-lead">{lead}</p>}
      </div>
      {actions && <div className="pf-block-actions">{actions}</div>}
    </header>
    {children}
  </section>
);
