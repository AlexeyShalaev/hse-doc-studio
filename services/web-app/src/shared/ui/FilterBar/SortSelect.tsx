import { useTranslation } from "react-i18next";
import type { ListSort } from "../../lib/serverList";
import { Select } from "../Select";

// Порядок строк выпадающим списком в панели фильтров. Нужен там, где поле
// сортировки не стоит отдельным столбцом (дата регистрации, почта) или
// столбцов нет вовсе (карточки групп). Сортирует сервер: список только
// выбирает поле и направление из разрешённых.

export type SortOption<S extends string> = {
  field: S;
  desc: boolean;
  label: string;
};

export type SortSelectProps<S extends string> = {
  sort: ListSort<S> | null;
  onChange: (sort: ListSort<S>) => void;
  options: readonly SortOption<S>[];
  /** Подпись слева; по умолчанию «Порядок». */
  label?: string | undefined;
  testId?: string | undefined;
};

const valueOf = (field: string, desc: boolean): string =>
  desc ? `-${field}` : field;

export const SortSelect = <S extends string>({
  sort,
  onChange,
  options,
  label,
  testId,
}: SortSelectProps<S>) => {
  const { t } = useTranslation("uiPrimitives");
  const caption = label ?? t("sortSelect.label");
  // Порядок, выбранный щелчком по столбцу, может не быть в списке: тогда
  // список показывает его как «по столбцу», а не первый попавшийся вариант.
  const current = sort ? valueOf(sort.field, sort.desc) : "";
  const known = options.some((o) => valueOf(o.field, o.desc) === current);
  return (
    <div className="fbar-group fbar-select" data-testid={testId}>
      <span className="fbar-caption" aria-hidden="true">
        {caption}
      </span>
      <Select
        value={current}
        ariaLabel={caption}
        placeholder={caption}
        onValueChange={(value) => {
          const option = options.find(
            (o) => valueOf(o.field, o.desc) === value,
          );
          if (option) onChange({ field: option.field, desc: option.desc });
        }}
        options={[
          ...options.map((o) => ({
            value: valueOf(o.field, o.desc),
            label: o.label,
          })),
          ...(known || current === ""
            ? []
            : [{ value: current, label: t("sortSelect.column") }]),
        ]}
      />
    </div>
  );
};

SortSelect.displayName = "SortSelect";
