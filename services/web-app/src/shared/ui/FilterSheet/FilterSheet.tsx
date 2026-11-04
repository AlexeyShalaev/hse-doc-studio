import { useState, type ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Modal } from "../Modal";

export type FilterSheetProps = {
  /** Сколько фильтров отличается от значений по умолчанию: число на кнопке. */
  activeCount: number;
  /** Группы фильтров (FilterSheetGroup) или любые поля. */
  children: ReactNode;
  /** Сброс к значениям по умолчанию; без него кнопки «Сбросить» нет. */
  onReset?: () => void;
  /** Подпись кнопки и заголовка шторки; по умолчанию «Фильтры». */
  label?: string;
  testId?: string;
};

/**
 * Фильтры телефона: вместо ряда переключателей над списком одна кнопка с числом включённых
 * фильтров, нажатие открывает шторку снизу (Modal). Выбор применяется сразу, шторка закрывается
 * кнопкой «Готово» или по фону. На десктопе ряд остаётся на месте: страница сама решает, что
 * показать (useIsPhoneWidth).
 */
export const FilterSheet = ({
  activeCount,
  children,
  onReset,
  label,
  testId = "filter-sheet",
}: FilterSheetProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [isOpen, setIsOpen] = useState(false);
  const title = label ?? t("filterSheet.title");
  return (
    <>
      <button
        type="button"
        className="btn filter-sheet-trigger"
        data-testid={`${testId}-trigger`}
        aria-haspopup="dialog"
        aria-label={
          activeCount > 0
            ? `${title}. ${t("filterSheet.active", { count: activeCount })}`
            : title
        }
        onClick={() => {
          setIsOpen(true);
        }}
      >
        <SlidersHorizontal size="0.9375rem" aria-hidden="true" />
        <span className="filter-sheet-label">
          {label ?? t("filterSheet.open")}
        </span>
        {activeCount > 0 && (
          <span className="filter-sheet-count" aria-hidden="true">
            {activeCount}
          </span>
        )}
      </button>
      <Modal
        isOpen={isOpen}
        onClose={() => {
          setIsOpen(false);
        }}
        title={title}
        footer={
          <>
            {onReset && activeCount > 0 && (
              <button
                type="button"
                className="btn ghost"
                data-testid={`${testId}-reset`}
                onClick={onReset}
              >
                {t("filterSheet.reset")}
              </button>
            )}
            <button
              type="button"
              className="btn primary"
              data-testid={`${testId}-done`}
              onClick={() => {
                setIsOpen(false);
              }}
            >
              {t("filterSheet.done")}
            </button>
          </>
        }
      >
        <div className="filter-sheet-groups" data-testid={testId}>
          {children}
        </div>
      </Modal>
    </>
  );
};

export type FilterSheetGroupProps = {
  label: string;
  children: ReactNode;
};

/** Группа фильтров в шторке: видимая подпись и переключатель на всю ширину. */
export const FilterSheetGroup = ({
  label,
  children,
}: FilterSheetGroupProps) => (
  <div className="filter-sheet-group">
    <div className="filter-sheet-group-label">{label}</div>
    {children}
  </div>
);
