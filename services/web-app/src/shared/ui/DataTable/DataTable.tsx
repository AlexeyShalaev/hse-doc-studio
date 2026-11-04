import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useIsPhoneWidth } from "../../lib/viewport";
import { EmptyState, ErrorState, NoResults } from "../EmptyState";
import { Pagination, type CursorPaginationProps } from "../Pagination";

// Таблица админских экранов. Сортировка и страницы серверные: таблица только
// показывает состояние и сообщает о намерении (onSortingChange, onPageChange).
// Сортируются только столбцы из sortable (поля, которые разрешил сервер);
// щелчок по заголовку меняет порядок по возрастанию и убыванию.

export type DataTablePagination = {
  mode?: "offset";
  /** Номер страницы с нуля. */
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  pageSizes?: readonly number[] | undefined;
  onPageSizeChange?: ((size: number) => void) | undefined;
  busy?: boolean | undefined;
};

export type DataTableProps<T> = {
  columns: ColumnDef<T>[];
  data: T[];
  getRowId: (row: T) => string;
  /** Название таблицы для скринридера. */
  caption: string;
  loading?: boolean;
  /** Сообщение об ошибке загрузки; показывается вместо строк. */
  error?: string | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  emptyAction?: React.ReactNode;
  /** Значок пустого состояния; по умолчанию «входящие». */
  emptyIcon?: React.ReactNode;
  /**
   * Ширины колонок по id: без них пустая таблица раскладывает шапку по-другому,
   * и колонки прыгают при смене фильтра.
   */
  columnWidths?: Partial<Record<string, number | string>>;
  sorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  /**
   * id столбцов, которые сортирует сервер. Без списка сортируются все
   * столбцы с accessor, кроме enableSorting: false.
   */
  sortable?: readonly string[];
  /** Страницы (offset) или «Показать ещё» (cursor). */
  pagination?: DataTablePagination | CursorPaginationProps;
  /**
   * Поиск или фильтры заданы: пустой ответ значит «ничего не найдено», а не
   * «пока пусто», и вместо действия создания кнопка сброса.
   */
  filtered?: boolean;
  onResetFilters?: () => void;
  /** Текущий поиск: попадает в пояснение «ничего не найдено». */
  searchQuery?: string;
  selectedRowId?: string | null;
  onRowClick?: (row: T) => void;
  /** Сколько строк-скелетов при загрузке. */
  skeletonRows?: number;
  /** Высота прокручиваемой области, px; шапка липкая. */
  maxHeight?: number;
  className?: string;
  /**
   * Вид на телефоне: `cards` (по умолчанию) - карточка на строку, `table` - прежняя таблица с
   * прокруткой внутри блока. Роли столбцов в карточке задаёт `meta.card` у столбца.
   */
  phone?: "cards" | "table";
};

export const DataTable = <T,>({
  columns,
  data,
  getRowId,
  caption,
  loading = false,
  error = null,
  onRetry,
  emptyTitle,
  emptyHint,
  emptyAction,
  emptyIcon,
  columnWidths,
  sorting = [],
  onSortingChange,
  sortable,
  pagination,
  filtered = false,
  onResetFilters,
  searchQuery,
  selectedRowId = null,
  onRowClick,
  skeletonRows = 5,
  maxHeight,
  className,
  phone = "cards",
}: DataTableProps<T>) => {
  const { t } = useTranslation("uiPrimitives");
  const isCards = useIsPhoneWidth() && phone === "cards";
  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: { sorting },
    manualSorting: true,
    manualPagination: true,
    // Сервер всегда сортирует хоть как-то: снять сортировку нельзя, только
    // поменять направление.
    enableSortingRemoval: false,
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      onSortingChange?.(next);
    },
    getCoreRowModel: getCoreRowModel(),
  });

  const colCount = columns.length;
  const showSkeleton = loading && data.length === 0 && !error;
  const showError = error != null;
  const showEmpty = !loading && !showError && data.length === 0;
  const busy = loading && !showSkeleton;

  if (isCards) {
    const renderHeader = (columnId: string): React.ReactNode => {
      const header = table
        .getFlatHeaders()
        .find((item) => item.column.id === columnId);
      return header
        ? flexRender(header.column.columnDef.header, header.getContext())
        : null;
    };
    return (
      <div
        className={clsx("dt-cards-wrap", className)}
        style={{ display: "flex", flexDirection: "column", gap: 10 }}
      >
        <div
          aria-label={caption}
          aria-busy={loading}
          role="list"
          className="dt-cards"
          style={{ opacity: busy ? 0.6 : 1 }}
        >
          {showSkeleton &&
            Array.from({ length: Math.min(skeletonRows, 3) }, (_, index) => (
              <div
                key={`sk-${String(index)}`}
                className="dt-card dt-card-skeleton"
                aria-hidden="true"
              />
            ))}
          {!showSkeleton &&
            !showError &&
            table.getRowModel().rows.map((row) => {
              const cells = row.getVisibleCells();
              const roleOf = (cell: (typeof cells)[number], index: number) =>
                cell.column.columnDef.meta?.card ??
                (cell.column.id === "actions"
                  ? "actions"
                  : index === 0
                    ? "title"
                    : "line");
              const byRole = (role: string) =>
                cells.filter((cell, index) => roleOf(cell, index) === role);
              const render = (cell: (typeof cells)[number]) =>
                flexRender(cell.column.columnDef.cell, cell.getContext());
              const selected = selectedRowId === row.id;
              const actions = byRole("actions");
              const badges = byRole("badges");
              return (
                <div
                  key={row.id}
                  role="listitem"
                  className="dt-card"
                  data-selected={selected ? "true" : undefined}
                  data-clickable={onRowClick ? "true" : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={
                    onRowClick
                      ? () => {
                          onRowClick(row.original);
                        }
                      : undefined
                  }
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.target !== event.currentTarget) return;
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onRowClick(row.original);
                          }
                        }
                      : undefined
                  }
                >
                  <div className="dt-card-head">
                    <div className="dt-card-title">
                      {byRole("title").map((cell) => (
                        <div key={cell.id}>{render(cell)}</div>
                      ))}
                    </div>
                    {actions.length > 0 && (
                      <div
                        className="dt-card-actions"
                        onClick={(event) => {
                          event.stopPropagation();
                        }}
                      >
                        {actions.map((cell) => (
                          <span key={cell.id}>{render(cell)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  {badges.length > 0 && (
                    <div className="dt-card-badges">
                      {badges.map((cell) => (
                        <span key={cell.id}>{render(cell)}</span>
                      ))}
                    </div>
                  )}
                  {byRole("line").length > 0 && (
                    <dl className="dt-card-lines">
                      {byRole("line").map((cell) => (
                        <div key={cell.id} className="dt-card-line">
                          <dt>{renderHeader(cell.column.id)}</dt>
                          <dd>{render(cell)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              );
            })}
          {showError && (
            <ErrorState
              title={t("dataTable.errorTitle")}
              description={error}
              onRetry={onRetry}
            />
          )}
          {showEmpty &&
            (filtered ? (
              <NoResults query={searchQuery} onReset={onResetFilters} />
            ) : (
              <EmptyState
                icon={emptyIcon}
                title={emptyTitle ?? t("dataTable.emptyTitle")}
                description={emptyHint}
                action={emptyAction ?? undefined}
              />
            ))}
        </div>
        {pagination && !showError && !showSkeleton && (
          <Pagination {...pagination} />
        )}
      </div>
    );
  }

  return (
    <div
      className={clsx(className)}
      style={{ display: "flex", flexDirection: "column", gap: 10 }}
    >
      <div
        className="card flat"
        style={{
          overflow: "auto",
          maxHeight,
          padding: 0,
          opacity: busy ? 0.6 : 1,
          transition: "opacity 0.12s",
        }}
      >
        <table
          aria-label={caption}
          aria-busy={loading}
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 12.5,
            // С заданными ширинами раскладка не зависит от содержимого строк.
            tableLayout: columnWidths ? "fixed" : undefined,
          }}
        >
          {columnWidths && (
            <colgroup>
              {table.getVisibleLeafColumns().map((column) => (
                <col
                  key={column.id}
                  style={
                    columnWidths[column.id] !== undefined
                      ? { width: columnWidths[column.id] }
                      : undefined
                  }
                />
              ))}
            </colgroup>
          )}
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  // С allowlist сортировку решает он: столбцу с одним cell
                  // (без accessor) TanStack сортировать не даёт, а серверу всё
                  // равно, как столбец нарисован.
                  const canSort =
                    onSortingChange != null &&
                    (sortable === undefined
                      ? header.column.getCanSort()
                      : sortable.includes(header.column.id) &&
                        header.column.columnDef.enableSorting !== false);
                  const current = sorting.find(
                    (item) => item.id === header.column.id,
                  );
                  const dir = current ? (current.desc ? "desc" : "asc") : false;
                  // Щелчок меняет направление; новый столбец начинает с
                  // sortDescFirst (даты и числа удобнее с новых).
                  const toggle = () => {
                    onSortingChange?.([
                      {
                        id: header.column.id,
                        desc: current
                          ? !current.desc
                          : header.column.columnDef.sortDescFirst === true,
                      },
                    ]);
                  };
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        dir === "asc"
                          ? "ascending"
                          : dir === "desc"
                            ? "descending"
                            : canSort
                              ? "none"
                              : undefined
                      }
                      style={{
                        position: "sticky",
                        top: 0,
                        zIndex: 1,
                        textAlign: "left",
                        padding: "9px 12px",
                        background: "var(--bg-2)",
                        borderBottom: "1px solid var(--border)",
                        color: "var(--fg-2)",
                        fontWeight: 500,
                        fontSize: 11.5,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          onClick={toggle}
                          style={{
                            all: "unset",
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                            color: dir ? "var(--fg-0)" : "inherit",
                          }}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {dir === "asc" ? (
                            <ArrowUp size={12} aria-hidden="true" />
                          ) : dir === "desc" ? (
                            <ArrowDown size={12} aria-hidden="true" />
                          ) : (
                            <ArrowUpDown
                              size={12}
                              aria-hidden="true"
                              className="dt-sort-hint"
                            />
                          )}
                          <span className="sr-only">
                            {dir === "asc"
                              ? t("dataTable.sortedAsc")
                              : dir === "desc"
                                ? t("dataTable.sortedDesc")
                                : t("dataTable.sortBy")}
                          </span>
                        </button>
                      ) : (
                        flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {showSkeleton &&
              Array.from({ length: skeletonRows }, (_, index) => (
                <tr key={`sk-${String(index)}`} aria-hidden="true">
                  {columns.map((_, cell) => (
                    <td key={cell} style={{ padding: "12px" }}>
                      <span
                        style={{
                          display: "block",
                          height: 10,
                          width: `${String(45 + ((index * 17 + cell * 23) % 45))}%`,
                          borderRadius: 4,
                          background: "var(--bg-3)",
                        }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            {!showSkeleton &&
              !showError &&
              table.getRowModel().rows.map((row) => {
                const selected = selectedRowId === row.id;
                return (
                  <tr
                    key={row.id}
                    aria-selected={onRowClick ? selected : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={
                      onRowClick
                        ? () => {
                            onRowClick(row.original);
                          }
                        : undefined
                    }
                    onKeyDown={
                      onRowClick
                        ? (event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              onRowClick(row.original);
                            }
                          }
                        : undefined
                    }
                    style={{
                      cursor: onRowClick ? "pointer" : undefined,
                      background: selected
                        ? "var(--accent-soft, var(--bg-2))"
                        : undefined,
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td
                        key={cell.id}
                        style={{
                          padding: "10px 12px",
                          color: "var(--fg-1)",
                          verticalAlign: "middle",
                        }}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
            {showError && (
              <tr>
                <td colSpan={colCount} style={{ padding: 0 }}>
                  <ErrorState
                    title={t("dataTable.errorTitle")}
                    description={error}
                    onRetry={onRetry}
                  />
                </td>
              </tr>
            )}
            {showEmpty && (
              <tr>
                <td colSpan={colCount} style={{ padding: 0 }}>
                  {/* Тот же вид, что у пустых состояний вне таблиц. */}
                  {filtered ? (
                    <NoResults query={searchQuery} onReset={onResetFilters} />
                  ) : (
                    <EmptyState
                      icon={emptyIcon}
                      title={emptyTitle ?? t("dataTable.emptyTitle")}
                      description={emptyHint}
                      action={emptyAction ?? undefined}
                    />
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {pagination && !showError && !showSkeleton && (
        <Pagination {...pagination} />
      )}
    </div>
  );
};

DataTable.displayName = "DataTable";
