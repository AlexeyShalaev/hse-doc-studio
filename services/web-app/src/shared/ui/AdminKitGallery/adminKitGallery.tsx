import { useState } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import type { GalleryGroup } from "../../lib/stateGallery";
import { ConfirmByName } from "../ConfirmByName";
import { DataTable } from "../DataTable";
import { FilterBar } from "../FilterBar";
import { SecretOnce } from "../SecretOnce";
import { StatusDot, type StatusDotStatus } from "../StatusDot";

// Группа галереи /dev/server-screens: примитивы админских экранов во всех
// состояниях. Данные демонстрационные.

type Runner = {
  id: string;
  name: string;
  status: StatusDotStatus;
  jobs: number;
};

const RUNNERS: Runner[] = [
  { id: "r1", name: "runner-msk-01", status: "online", jobs: 128 },
  { id: "r2", name: "runner-msk-02", status: "stale", jobs: 64 },
  { id: "r3", name: "runner-spb-01", status: "offline", jobs: 0 },
  { id: "r4", name: "runner-lab-01", status: "paused", jobs: 12 },
  { id: "r5", name: "runner-lab-02", status: "degraded", jobs: 7 },
];

const COLUMNS: ColumnDef<Runner>[] = [
  { accessorKey: "name", header: "Раннер" },
  {
    accessorKey: "status",
    header: "Состояние",
    enableSorting: false,
    cell: ({ row }) => <StatusDot status={row.original.status} />,
  },
  { accessorKey: "jobs", header: "Задач" },
];

const TableDemo = ({ initialSort = [] as SortingState }) => {
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const first = sorting[0];
  const rows = [...RUNNERS].sort((a, b) => {
    if (!first) return 0;
    const k = first.id as keyof Runner;
    const r = String(a[k]).localeCompare(String(b[k]), undefined, {
      numeric: true,
    });
    return first.desc ? -r : r;
  });
  return (
    <DataTable
      caption="Раннеры"
      columns={COLUMNS}
      data={rows.slice(page * 3, page * 3 + 3)}
      getRowId={(r) => r.id}
      sorting={sorting}
      onSortingChange={setSorting}
      selectedRowId={selected}
      onRowClick={(r) => {
        setSelected(r.id);
      }}
      pagination={{
        page,
        pageSize: 3,
        total: rows.length,
        onPageChange: setPage,
      }}
    />
  );
};

const FilterDemo = () => {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  return (
    <FilterBar
      search={search}
      onSearchChange={setSearch}
      searchPlaceholder="Имя или e-mail"
      filters={[
        {
          id: "status",
          label: "Статус",
          value: status,
          onChange: setStatus,
          options: [
            { value: "active", label: "Активные", count: 42 },
            { value: "pending", label: "Ждут одобрения", count: 3 },
            { value: "disabled", label: "Отключены", count: 1 },
          ],
        },
      ]}
      onReset={() => {
        setSearch("");
        setStatus("");
      }}
    />
  );
};

const ConfirmDemo = ({ pending = false, error = null as string | null }) => (
  <ConfirmByName
    isOpen
    onClose={() => undefined}
    onConfirm={() => undefined}
    name="hse-cs"
    title="Удалить организацию"
    description="Участники потеряют доступ к проектам организации. Действие нельзя отменить."
    confirmLabel="Удалить"
    pending={pending}
    error={error}
  />
);

const noop = () => undefined;

export const getAdminKitGallery = (): GalleryGroup[] => [
  {
    id: "admin-data-table",
    title: "Таблица админки",
    description: "Серверная сортировка и страницы, липкая шапка.",
    entries: [
      {
        id: "admin_table_data",
        title: "Данные, сортировка и страницы",
        note: "Заголовки столбцов сортируют, строка выбирается мышью и клавиатурой.",
        frame: "window",
        width: 640,
        render: () => <TableDemo />,
      },
      {
        id: "admin_table_loading",
        title: "Загрузка",
        frame: "window",
        width: 640,
        render: () => (
          <DataTable
            caption="Раннеры"
            columns={COLUMNS}
            data={[]}
            getRowId={(r) => r.id}
            loading
          />
        ),
      },
      {
        id: "admin_table_empty",
        title: "Пусто",
        note: "Подсказка и действие для первого шага.",
        frame: "window",
        width: 640,
        render: () => (
          <DataTable
            caption="Раннеры"
            columns={COLUMNS}
            data={[]}
            getRowId={(r) => r.id}
            emptyTitle="Раннеров пока нет"
            emptyHint="Создайте токен и запустите раннер на своей машине."
            emptyAction={
              <button type="button" className="btn primary">
                Создать токен
              </button>
            }
          />
        ),
      },
      {
        id: "admin_table_error",
        title: "Ошибка загрузки",
        frame: "window",
        width: 640,
        render: () => (
          <DataTable
            caption="Раннеры"
            columns={COLUMNS}
            data={[]}
            getRowId={(r) => r.id}
            error="Сервер не ответил. Проверьте соединение."
            onRetry={noop}
          />
        ),
      },
    ],
  },
  {
    id: "admin-filter-bar",
    title: "Поиск и фильтры",
    entries: [
      {
        id: "admin_filter_bar",
        title: "Поиск с задержкой и чипы",
        frame: "window",
        width: 720,
        render: () => <FilterDemo />,
      },
    ],
  },
  {
    id: "admin-confirm-by-name",
    title: "Подтверждение вводом названия",
    entries: [
      {
        id: "admin_confirm_idle",
        title: "Ожидает ввода",
        note: "Кнопка активна только при точном совпадении названия.",
        frame: "window",
        width: 560,
        render: () => <ConfirmDemo />,
      },
      {
        id: "admin_confirm_pending",
        title: "Удаление идёт",
        frame: "window",
        width: 560,
        render: () => <ConfirmDemo pending />,
      },
      {
        id: "admin_confirm_error",
        title: "Ошибка",
        frame: "window",
        width: 560,
        render: () => (
          <ConfirmDemo error="Не удалось удалить: у организации есть проекты." />
        ),
      },
    ],
  },
  {
    id: "admin-secret-once",
    title: "Секрет, показанный один раз",
    entries: [
      {
        id: "admin_secret_once",
        title: "Токен раннера",
        note: "Закрытие без копирования просит подтверждения.",
        frame: "window",
        width: 560,
        render: () => (
          <SecretOnce
            label="Токен раннера"
            value="rt_9Qw3Zk7LmP2xVb8Nd4Hs6TfYc1Ra5Ue0"
            hint="Вставьте его в настройки раннера."
            onClose={noop}
          />
        ),
      },
    ],
  },
  {
    id: "admin-status-dot",
    title: "Индикатор состояния",
    description: "Форма точки и подпись различимы без цвета.",
    entries: [
      {
        id: "admin_status_dots",
        title: "Все состояния",
        frame: "window",
        width: 420,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {(
              ["online", "stale", "offline", "paused", "degraded"] as const
            ).map((s) => (
              <StatusDot key={s} status={s} />
            ))}
          </div>
        ),
      },
    ],
  },
];
