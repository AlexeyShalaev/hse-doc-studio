import { useId, useState, type ReactNode } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { localeTag } from "../../lib/i18n/localeTag";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import type { FilterOption } from "./FilterBar";

// Фильтр-кнопка с выпадающим списком значений: несколько значений сразу
// (статусы, роли, виды задач). Выбор применяется сразу, без «Готово»; числа
// справа приходят с сервера (facets). Длинный список получает поле, которое
// сужает сами варианты фильтра (это перечисление, а не строки таблицы).

export type FilterMenuProps = {
  label: string;
  options: FilterOption[];
  values: readonly string[];
  onChange: (values: string[]) => void;
  /** Одно значение: выбор заменяет прежний, как у переключателя. */
  single?: boolean | undefined;
  /** Значок перед подписью кнопки. */
  icon?: ReactNode | undefined;
  testId?: string | undefined;
};

const SEARCHABLE_FROM = 9;

/** Подпись выбранного на кнопке: одно значение по имени, больше числом. */
export const FilterTriggerText = ({
  label,
  summary,
}: {
  label: string;
  summary: string | null;
}) => (
  <>
    <span className="fmenu-label">{label}</span>
    {summary && (
      <>
        <span aria-hidden="true" className="fmenu-sep">
          :
        </span>
        <span className="fmenu-value">{summary}</span>
      </>
    )}
  </>
);

export const FilterMenu = ({
  label,
  options,
  values,
  onChange,
  single = false,
  icon,
  testId,
}: FilterMenuProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [open, setOpen] = useState(false);
  const [narrow, setNarrow] = useState("");
  const listId = useId();
  const chosen = options.filter((o) => values.includes(o.value));
  const summary =
    chosen.length === 0
      ? null
      : chosen.length === 1
        ? (chosen[0]?.label ?? null)
        : t("filterMenu.selected", { count: chosen.length });
  const shown =
    options.length >= SEARCHABLE_FROM && narrow.trim()
      ? options.filter((o) =>
          o.label.toLowerCase().includes(narrow.trim().toLowerCase()),
        )
      : options;

  const toggle = (value: string) => {
    if (single) {
      onChange(values.includes(value) ? [] : [value]);
      setOpen(false);
      return;
    }
    onChange(
      values.includes(value)
        ? values.filter((v) => v !== value)
        : [...values, value],
    );
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setNarrow("");
      }}
    >
      <span className={clsx("fmenu", chosen.length > 0 && "is-active")}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="fmenu-trigger"
            aria-haspopup="dialog"
            data-testid={testId}
          >
            {icon}
            <FilterTriggerText label={label} summary={summary} />
            <ChevronDown size={13} aria-hidden="true" />
          </button>
        </PopoverTrigger>
        {chosen.length > 0 && (
          <button
            type="button"
            className="fmenu-clear"
            aria-label={t("filterMenu.clearOne", { label })}
            title={t("filterMenu.clear")}
            onClick={() => {
              onChange([]);
            }}
          >
            <X size={12} aria-hidden="true" />
          </button>
        )}
      </span>
      <PopoverContent width={260} align="start" aria-label={label}>
        {options.length >= SEARCHABLE_FROM && (
          <input
            className="combo-input"
            value={narrow}
            placeholder={t("filterMenu.narrow")}
            aria-label={t("filterMenu.narrow")}
            aria-controls={listId}
            autoFocus
            onChange={(event) => {
              setNarrow(event.target.value);
            }}
          />
        )}
        <div
          id={listId}
          role={single ? "radiogroup" : "group"}
          aria-label={label}
          className="fmenu-list"
        >
          {shown.map((option) => {
            const on = values.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                role={single ? "radio" : "checkbox"}
                aria-checked={on}
                className="fmenu-item"
                onClick={() => {
                  toggle(option.value);
                }}
              >
                <span
                  className={clsx("fmenu-box", single && "is-radio")}
                  data-on={on ? "true" : undefined}
                  aria-hidden="true"
                >
                  {on && <Check size={11} />}
                </span>
                <span className="fmenu-text">{option.label}</span>
                {option.count != null && (
                  <span className="fmenu-count">
                    {option.count.toLocaleString(localeTag())}
                  </span>
                )}
              </button>
            );
          })}
          {shown.length === 0 && (
            <p className="combo-empty">{t("combobox.emptyText")}</p>
          )}
        </div>
        {values.length > 0 && !single && (
          <div className="fmenu-foot">
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => {
                onChange([]);
              }}
            >
              {t("filterMenu.clear")}
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
};

FilterMenu.displayName = "FilterMenu";
