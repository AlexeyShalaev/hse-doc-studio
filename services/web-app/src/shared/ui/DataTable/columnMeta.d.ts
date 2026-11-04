import "@tanstack/react-table";

declare module "@tanstack/react-table" {
  // Параметры обязаны повторять объявление пакета, иначе слияние интерфейсов не сработает.
  /* eslint-disable @typescript-eslint/no-unused-vars, @typescript-eslint/consistent-type-definitions */
  interface ColumnMeta<TData extends RowData, TValue> {
    /**
     * Где столбец в карточке на телефоне (DataTable). `title` - название карточки (по умолчанию
     * первый столбец), `actions` - кнопки в углу (по умолчанию столбец с id "actions"), `badges` -
     * строка значков, `line` - подпись и значение (по умолчанию остальные), `hidden` - не показывать.
     */
    card?: "title" | "line" | "badges" | "actions" | "hidden";
  }
  /* eslint-enable @typescript-eslint/no-unused-vars, @typescript-eslint/consistent-type-definitions */
}
