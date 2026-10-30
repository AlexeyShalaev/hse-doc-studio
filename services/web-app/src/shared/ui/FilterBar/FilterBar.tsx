import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useDebouncedValue } from "../../lib/useDebouncedValue";

// Панель над таблицей: поиск с задержкой и группы фильтров-чипов. Каждая группа
// выбирает одно значение; пустое значение значит «все».

export type FilterOption = { value: string; label: string; count?: number };

export type FilterGroup = {
  id: string;
  /** Название группы для скринридера и подписи. */
  label: string;
  options: FilterOption[];
  /** Выбранное значение; "" значит «все». */
  value: string;
  onChange: (value: string) => void;
};

export type FilterBarProps = {
  /** Текущий поисковый запрос (после задержки). */
  search: string;
  /** Вызывается после паузы в наборе. */
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  searchLabel?: string;
  debounceMs?: number;
  filters?: FilterGroup[];
  /** Сбросить поиск и все фильтры. */
  onReset?: () => void;
  className?: string;
};

export const FilterBar = ({
  search,
  onSearchChange,
  searchPlaceholder,
  searchLabel,
  debounceMs = 300,
  filters = [],
  onReset,
  className,
}: FilterBarProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [text, setText] = useState(search);
  const debounced = useDebouncedValue(text, debounceMs);
  const last = useRef(search);

  // Внешний сброс поиска возвращает поле в исходное состояние.
  useEffect(() => {
    if (search !== last.current) {
      last.current = search;
      setText(search);
    }
  }, [search]);

  useEffect(() => {
    if (debounced !== last.current) {
      last.current = debounced;
      onSearchChange(debounced);
    }
  }, [debounced, onSearchChange]);

  const active = text !== "" || filters.some((f) => f.value !== "");

  return (
    <div
      role="search"
      className={clsx(className)}
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 10,
        alignItems: "center",
      }}
    >
      <div style={{ position: "relative", flex: "1 1 220px", maxWidth: 360 }}>
        <Search
          size={14}
          aria-hidden="true"
          style={{
            position: "absolute",
            left: 10,
            top: "50%",
            transform: "translateY(-50%)",
            color: "var(--fg-3)",
            pointerEvents: "none",
          }}
        />
        <input
          type="search"
          className="input"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
          }}
          placeholder={searchPlaceholder ?? t("filterBar.searchPlaceholder")}
          aria-label={searchLabel ?? t("filterBar.search")}
          style={{ width: "100%", paddingLeft: 30 }}
        />
      </div>
      {filters.map((group) => (
        <div
          key={group.id}
          role="group"
          aria-label={group.label}
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <Chip
            selected={group.value === ""}
            onClick={() => {
              group.onChange("");
            }}
          >
            {t("filterBar.all")}
          </Chip>
          {group.options.map((option) => (
            <Chip
              key={option.value}
              selected={group.value === option.value}
              onClick={() => {
                group.onChange(option.value);
              }}
            >
              {option.label}
              {option.count != null && (
                <span
                  style={{
                    color: "var(--fg-2)",
                    marginLeft: 2,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {option.count}
                </span>
              )}
            </Chip>
          ))}
        </div>
      ))}
      {onReset && active && (
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            setText("");
            onReset();
          }}
        >
          <X size={12} aria-hidden="true" />
          {t("filterBar.reset")}
        </button>
      )}
    </div>
  );
};

const Chip = ({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) => (
  <button
    type="button"
    className={clsx("chip sans", selected && "accent")}
    aria-pressed={selected}
    onClick={onClick}
    style={{ cursor: "pointer", height: 26, padding: "0 10px", fontSize: 12 }}
  >
    {children}
  </button>
);

FilterBar.displayName = "FilterBar";
