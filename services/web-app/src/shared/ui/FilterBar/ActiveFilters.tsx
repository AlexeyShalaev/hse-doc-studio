import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { localeTag } from "../../lib/i18n/localeTag";

// Строка «что сейчас отобрано»: чип на каждое условие с крестиком и одна
// кнопка «Сбросить». Слева сколько нашлось, если сервер дал число.

export type ActiveFilter = {
  id: string;
  /** Название условия: «Статус», «Человек». */
  label: string;
  /** Выбранное значение словами: «Активные», «Мария Келлер». */
  value: string;
  onRemove: () => void;
};

export type ActiveFiltersProps = {
  items: ActiveFilter[];
  onReset: () => void;
  /** Сколько строк нашлось при этих условиях. */
  total?: number | null | undefined;
};

export const ActiveFilters = ({
  items,
  onReset,
  total,
}: ActiveFiltersProps) => {
  const { t } = useTranslation("uiPrimitives");
  if (items.length === 0) return null;
  return (
    <div className="factive" role="group" aria-label={t("activeFilters.label")}>
      {total != null && (
        <span className="factive-total" aria-live="polite">
          {t("activeFilters.found", {
            count: total,
            n: total.toLocaleString(localeTag()),
          })}
        </span>
      )}
      {items.map((item) => (
        <span key={item.id} className="factive-chip">
          <span className="factive-name">{item.label}:</span>
          <span className="factive-value">{item.value}</span>
          <button
            type="button"
            aria-label={t("activeFilters.remove", {
              label: item.label,
              value: item.value,
            })}
            onClick={item.onRemove}
          >
            <X size={11} aria-hidden="true" />
          </button>
        </span>
      ))}
      <button type="button" className="btn ghost sm" onClick={onReset}>
        {t("filterBar.reset")}
      </button>
    </div>
  );
};

ActiveFilters.displayName = "ActiveFilters";
