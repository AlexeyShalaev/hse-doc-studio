import { useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { FilterTriggerText } from "./FilterMenu";

// Сортировка списка без шапки таблицы (строки-карточки): поле из разрешённых
// сервером и направление. Таблицам она не нужна, там сортирует щелчок по
// заголовку. Снять сортировку нельзя: сервер всегда отдаёт строки в
// каком-то порядке.

export type SortMenuOption<S extends string> = {
  field: S;
  label: string;
  /** Новое поле сначала по убыванию (даты: сначала новые). */
  descFirst?: boolean | undefined;
};

export type SortMenuValue<S extends string> = { field: S; desc: boolean };

export type SortMenuProps<S extends string> = {
  /** Подпись кнопки; по умолчанию «Сортировка». */
  label?: string | undefined;
  options: readonly SortMenuOption<S>[];
  value: SortMenuValue<S> | null;
  onChange: (next: SortMenuValue<S>) => void;
  testId?: string | undefined;
};

export const SortMenu = <S extends string>({
  label,
  options,
  value,
  onChange,
  testId,
}: SortMenuProps<S>) => {
  const { t } = useTranslation("uiPrimitives");
  const [open, setOpen] = useState(false);
  const title = label ?? t("sortMenu.label");
  const current = options.find((o) => o.field === value?.field) ?? null;
  const Direction = value?.desc ? ArrowDown : ArrowUp;

  const pickField = (option: SortMenuOption<S>) => {
    if (option.field === value?.field) return;
    onChange({ field: option.field, desc: option.descFirst === true });
  };
  const pickDirection = (desc: boolean) => {
    if (!value || value.desc === desc) return;
    onChange({ field: value.field, desc });
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <span className="fmenu is-sort">
        <PopoverTrigger asChild>
          <button
            type="button"
            className="fmenu-trigger"
            aria-haspopup="dialog"
            data-testid={testId}
          >
            <FilterTriggerText label={title} summary={current?.label ?? null} />
            {current && (
              <Direction
                size={12}
                aria-label={t(value?.desc ? "sortMenu.desc" : "sortMenu.asc")}
              />
            )}
            <ChevronDown size={13} aria-hidden="true" />
          </button>
        </PopoverTrigger>
      </span>
      <PopoverContent width={240} align="start" aria-label={title}>
        <div
          role="radiogroup"
          aria-label={t("sortMenu.field")}
          className="fmenu-list"
        >
          {options.map((option) => (
            <SortItem
              key={option.field}
              on={option.field === value?.field}
              onClick={() => {
                pickField(option);
              }}
            >
              {option.label}
            </SortItem>
          ))}
        </div>
        <div
          role="radiogroup"
          aria-label={t("sortMenu.direction")}
          className="fmenu-list"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <SortItem
            on={value?.desc === false}
            disabled={!value}
            icon={<ArrowUp size={12} aria-hidden="true" />}
            onClick={() => {
              pickDirection(false);
            }}
          >
            {t("sortMenu.asc")}
          </SortItem>
          <SortItem
            on={value?.desc === true}
            disabled={!value}
            icon={<ArrowDown size={12} aria-hidden="true" />}
            onClick={() => {
              pickDirection(true);
            }}
          >
            {t("sortMenu.desc")}
          </SortItem>
        </div>
      </PopoverContent>
    </Popover>
  );
};

const SortItem = ({
  on,
  disabled = false,
  icon,
  onClick,
  children,
}: {
  on: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  onClick: () => void;
  children: ReactNode;
}) => (
  <button
    type="button"
    role="radio"
    aria-checked={on}
    disabled={disabled}
    className="fmenu-item"
    onClick={onClick}
  >
    <span
      className="fmenu-box is-radio"
      data-on={on ? "true" : undefined}
      aria-hidden="true"
    >
      {on && <Check size={11} />}
    </span>
    <span className="fmenu-text">{children}</span>
    {icon}
  </button>
);

SortMenu.displayName = "SortMenu";
