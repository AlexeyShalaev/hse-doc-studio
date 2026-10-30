import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Users } from "lucide-react";
import type { GalleryGroup } from "../../lib/stateGallery";
import {
  useCursorList,
  useListQueryState,
  useServerList,
} from "../../lib/serverList";
import type {
  CursorPage,
  ListPage,
  ListRequestParams,
  PickerItem,
} from "../../lib/serverList/types";
import { DataTable } from "../DataTable";
import { EmptyState, NoResults } from "../EmptyState";
import {
  ActiveFilters,
  DateRangeFilter,
  FilterBar,
  FilterMenu,
} from "../FilterBar";
import { Pagination } from "../Pagination";
import { PersonCell } from "../PersonCell";
import {
  Picker,
  PickerFilter,
  usePickedItem,
  type PickerSource,
} from "../Picker";
import { SearchInput } from "../SearchInput";

// Галерея серверных списков: состояние в адресе, листание, поиск, фильтры и
// пикеры. «Сервер» здесь — функции ниже с задержкой: они ищут, фильтруют,
// сортируют и режут страницу так же, как это делает API, а экран получает
// только одну страницу. Данные демонстрационные.

const FIRST = [
  "Мария",
  "Иван",
  "Анна",
  "Пётр",
  "Елена",
  "Дмитрий",
  "Ольга",
  "Никита",
];
const LAST = [
  "Келлер",
  "Сидоров",
  "Петрова",
  "Орлов",
  "Миронова",
  "Кузнецов",
  "Белова",
  "Фёдоров",
];
const STATUSES = ["active", "pending_approval", "disabled"] as const;
const STATUS_LABEL: Record<(typeof STATUSES)[number], string> = {
  active: "Активен",
  pending_approval: "Ждёт одобрения",
  disabled: "Отключён",
};

type Person = {
  id: string;
  name: string;
  email: string;
  status: (typeof STATUSES)[number];
  org: string;
  created: number;
};

const ORGS = ["msp-2025", "ai-lab", "pilot-2026", "fkn"] as const;

// 12 345 человек строятся по номеру: те же при каждом открытии.
const personAt = (i: number): Person => {
  const first = FIRST[i % FIRST.length] ?? "";
  const last = LAST[Math.floor(i / FIRST.length) % LAST.length] ?? "";
  return {
    id: `u${String(i)}`,
    name: `${first} ${last} ${String(i)}`,
    email: `user${String(i)}@edu.hse.ru`,
    status: STATUSES[i % 17 === 0 ? 2 : i % 41 === 0 ? 1 : 0],
    org: ORGS[i % ORGS.length] ?? "fkn",
    created: Date.UTC(2026, 0, 1) + i * 3_600_000,
  };
};
const PEOPLE = Array.from({ length: 12_345 }, (_, i) => personAt(i));

const wait = (ms: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
const list = (value: ListRequestParams[string] | undefined): string[] =>
  value === undefined ? [] : Array.isArray(value) ? value : [String(value)];

/** «Сервер» списка людей: поиск, фильтры, сортировка и окно. */
const fetchPeople = async (
  params: ListRequestParams,
): Promise<ListPage<Person>> => {
  await wait(250);
  const q = String(params.q ?? "").toLowerCase();
  const statuses = list(params.status);
  const org = list(params.org)[0];
  const sort = String(params.sort ?? "-created");
  const desc = sort.startsWith("-");
  const field = (desc ? sort.slice(1) : sort) as "name" | "created";
  const found = PEOPLE.filter(
    (p) =>
      (!q || p.name.toLowerCase().includes(q) || p.email.includes(q)) &&
      (statuses.length === 0 || statuses.includes(p.status)) &&
      (!org || p.org === org),
  ).sort((a, b) => {
    const r =
      field === "name" ? a.name.localeCompare(b.name) : a.created - b.created;
    return desc ? -r : r;
  });
  const limit = Number(params.limit);
  const offset = Number(params.offset ?? 0);
  return {
    items: found.slice(offset, offset + limit),
    total: found.length,
    limit,
    offset,
  };
};

const ORG_ITEMS: PickerItem[] = ORGS.map((slug) => ({
  kind: "org",
  id: slug,
  name:
    slug === "fkn"
      ? "Студенты ФКН"
      : slug === "ai-lab"
        ? "Лаборатория ИИ"
        : slug === "pilot-2026"
          ? "Пилот 2026"
          : "МСПИН 2025",
  detail: slug,
}));

const pickerSource = (
  key: string,
  items: () => PickerItem[],
): PickerSource => ({
  key: ["gallery", key],
  search: async (q, { limit }) => {
    await wait(200);
    const needle = q.toLowerCase();
    const found = items().filter(
      (i) =>
        i.name.toLowerCase().includes(needle) ||
        (i.detail ?? "").toLowerCase().includes(needle),
    );
    return { items: found.slice(0, limit), has_more: found.length > limit };
  },
  resolve: (id) => Promise.resolve(items().find((i) => i.id === id) ?? null),
});

const ORG_SOURCE = pickerSource("orgs", () => ORG_ITEMS);
const PEOPLE_SOURCE = pickerSource("people", () =>
  PEOPLE.slice(0, 400).map((p): PickerItem => ({
    kind: "user",
    id: p.id,
    name: p.name,
    detail: p.email,
  })),
);

const COLUMNS: ColumnDef<Person>[] = [
  {
    id: "name",
    header: "Человек",
    cell: ({ row }) => (
      <PersonCell
        id={row.original.id}
        name={row.original.name}
        email={row.original.email}
      />
    ),
  },
  {
    id: "status",
    header: "Состояние",
    cell: ({ row }) => STATUS_LABEL[row.original.status],
  },
  {
    id: "created",
    header: "Создан",
    sortDescFirst: true,
    cell: ({ row }) =>
      new Date(row.original.created).toLocaleDateString("ru-RU"),
  },
];

const PEOPLE_OPTIONS = {
  prefix: "kit.",
  filters: {
    status: { multi: true, values: STATUSES },
    org: {},
  },
  sort: { fields: ["name", "created"] as const, default: "-created" as const },
};

/** Полный экран списка: адрес, поиск, фильтры, сортировка, страницы. */
const ServerTableDemo = () => {
  const state = useListQueryState(PEOPLE_OPTIONS);
  const people = useServerList({
    state,
    queryKey: ["gallery", "people"],
    fetchPage: fetchPeople,
  });
  const org = usePickedItem(ORG_SOURCE, state.filter("org") || null, null);
  const statusLabels = state.filters.status.map(
    (s) => STATUS_LABEL[s as Person["status"]],
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <FilterBar
        search={state.q}
        onSearchChange={state.setQ}
        searchPlaceholder="Имя или e-mail"
        busy={people.isFetching}
        onReset={state.reset}
        total={people.total}
        extra={
          <>
            <FilterMenu
              label="Состояние"
              values={state.filters.status}
              onChange={(values) => {
                state.setFilter("status", values);
              }}
              options={STATUSES.map((s) => ({
                value: s,
                label: STATUS_LABEL[s],
                count: s === "active" ? 11_403 : s === "disabled" ? 727 : 215,
              }))}
            />
            <PickerFilter
              label="Организация"
              source={ORG_SOURCE}
              value={state.filter("org") || null}
              onChange={(item) => {
                state.setFilter("org", item?.id ?? null);
              }}
            />
          </>
        }
        active={[
          ...(state.q
            ? [
                {
                  id: "q",
                  label: "Поиск",
                  value: state.q,
                  onRemove: () => {
                    state.setQ("");
                  },
                },
              ]
            : []),
          ...(statusLabels.length
            ? [
                {
                  id: "status",
                  label: "Состояние",
                  value: statusLabels.join(", "),
                  onRemove: () => {
                    state.setFilter("status", null);
                  },
                },
              ]
            : []),
          ...(state.filter("org")
            ? [
                {
                  id: "org",
                  label: "Организация",
                  value: org?.name ?? state.filter("org"),
                  onRemove: () => {
                    state.setFilter("org", null);
                  },
                },
              ]
            : []),
        ]}
      />
      <DataTable
        caption="Люди"
        columns={COLUMNS}
        data={people.items}
        getRowId={(p) => p.id}
        loading={people.isFetching}
        error={people.isError ? "Сервер не ответил." : null}
        onRetry={() => {
          void people.refetch();
        }}
        sorting={state.sorting}
        onSortingChange={state.onSortingChange}
        sortable={PEOPLE_OPTIONS.sort.fields}
        pagination={people.pagination}
        filtered={state.isFiltered}
        searchQuery={state.q}
        onResetFilters={state.reset}
        emptyTitle="Людей пока нет"
        columnWidths={{ status: 160, created: 130 }}
      />
    </div>
  );
};

type LogRow = { id: number; at: number; action: string };
const ACTIONS = [
  "auth.login",
  "org.member_add",
  "project.create",
  "runner.pause",
];
const LOG_SIZE = 250_000;
const logAt = (id: number): LogRow => ({
  id,
  at: Date.UTC(2026, 9, 30) - (LOG_SIZE - id) * 120_000,
  action: ACTIONS[id % ACTIONS.length] ?? "auth.login",
});

/** «Сервер» журнала: строки по id, новые первыми, курсор — id последней. */
const fetchLog = async (
  params: ListRequestParams & { cursor?: string },
): Promise<CursorPage<LogRow>> => {
  await wait(250);
  const limit = Number(params.limit);
  const from = params.from ? Date.parse(String(params.from)) : null;
  const to = params.to ? Date.parse(String(params.to)) : null;
  const items: LogRow[] = [];
  let id = params.cursor ? Number(params.cursor) - 1 : LOG_SIZE;
  for (; id >= 1 && items.length <= limit; id -= 1) {
    const row = logAt(id);
    if (to !== null && row.at >= to) continue;
    if (from !== null && row.at < from) break;
    items.push(row);
  }
  const page = items.slice(0, limit);
  const last = page[page.length - 1];
  return {
    items: page,
    next_cursor: items.length > limit && last ? String(last.id) : null,
    total_estimate: from === null && to === null ? LOG_SIZE : null,
  };
};

const LogDemo = () => {
  const state = useListQueryState({
    prefix: "log.",
    mode: "cursor",
    pageSize: 25,
    filters: { from: { date: "from" }, to: { date: "to" } },
  });
  const log = useCursorList({
    state,
    queryKey: ["gallery", "log"],
    fetchPage: fetchLog,
    getId: (row) => String(row.id),
  });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="fbar">
        <DateRangeFilter
          value={{
            from: state.filter("from") || null,
            to: state.filter("to") || null,
          }}
          onChange={({ from, to }) => {
            state.setFilters({ from, to });
          }}
        />
      </div>
      <div
        className="card flat"
        style={{ padding: 0, maxHeight: 260, overflow: "auto" }}
      >
        {log.items.map((row) => (
          <div
            key={row.id}
            style={{
              display: "flex",
              gap: 12,
              padding: "6px 12px",
              borderBottom: "1px solid var(--border)",
              fontSize: 12.5,
            }}
          >
            <span className="mono" style={{ color: "var(--fg-2)", width: 70 }}>
              {row.id}
            </span>
            <span style={{ flex: 1 }}>{row.action}</span>
            <span style={{ color: "var(--fg-2)" }}>
              {new Date(row.at).toLocaleString("ru-RU")}
            </span>
          </div>
        ))}
        {log.items.length === 0 && !log.isLoading && (
          <NoResults onReset={state.reset} compact />
        )}
      </div>
      <Pagination {...log.pagination} />
    </div>
  );
};

const PickerDemo = () => {
  const [person, setPerson] = useState<PickerItem | null>(null);
  const [org, setOrg] = useState<string | null>(null);
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
        minHeight: 360,
      }}
    >
      <label
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          fontSize: 12.5,
        }}
      >
        Добавить участника
        <Picker
          label="Человек"
          source={PEOPLE_SOURCE}
          value={person}
          onChange={setPerson}
          placeholder="Найдите человека по имени или почте"
          clearable
        />
      </label>
      <div className="fbar">
        <PickerFilter
          label="Организация"
          source={ORG_SOURCE}
          value={org}
          onChange={(item) => {
            setOrg(item?.id ?? null);
          }}
        />
      </div>
    </div>
  );
};

const SearchDemo = ({ busy = false, initial = "" }) => {
  const [q, setQ] = useState(initial);
  return (
    <SearchInput
      value={q}
      onChange={setQ}
      busy={busy}
      placeholder="Имя или e-mail"
    />
  );
};

const PaginationStates = () => {
  const [page, setPage] = useState(4);
  const [size, setSize] = useState(50);
  const sizes = useMemo(() => [25, 50, 100, 200], []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <Pagination
        page={page}
        pageSize={size}
        total={12_345}
        onPageChange={setPage}
        pageSizes={sizes}
        onPageSizeChange={(next) => {
          setSize(next);
          setPage(0);
        }}
      />
      <Pagination
        page={0}
        pageSize={50}
        total={37}
        onPageChange={() => undefined}
      />
      <Pagination
        mode="cursor"
        shown={150}
        hasMore
        onLoadMore={() => undefined}
        totalEstimate={250_000}
      />
      <Pagination
        mode="cursor"
        shown={75}
        hasMore
        loading
        onLoadMore={() => undefined}
        totalEstimate={null}
      />
      <Pagination
        mode="cursor"
        shown={21}
        hasMore={false}
        onLoadMore={() => undefined}
      />
    </div>
  );
};

export const getServerListGallery = (): GalleryGroup[] => [
  {
    id: "admin-server-list",
    title: "Серверный список",
    description:
      "useListQueryState + useServerList: поиск, фильтры, сортировка и страница в адресе (kit.q, kit.status, kit.sort, kit.page, kit.size); смена условий возвращает на первую страницу, прежние строки видны до ответа. 12 345 строк, «сервер» отдаёт одну страницу.",
    entries: [
      {
        id: "admin_server_table",
        title: "Люди: поиск, фильтры, сортировка, страницы",
        note: "Сортируются только «Человек» и «Создан». Номер страницы можно ввести.",
        frame: "window",
        width: 980,
        render: () => <ServerTableDemo />,
      },
      {
        id: "admin_server_log",
        title: "Журнал: курсор и период",
        note: "«Показать ещё» копит страницы; с периодом «из N» не пишется.",
        frame: "window",
        width: 720,
        render: () => <LogDemo />,
      },
    ],
  },
  {
    id: "admin-pagination",
    title: "Листание",
    description:
      "Pagination: offset с диапазоном, номером страницы и размером; cursor с «Показать ещё».",
    entries: [
      {
        id: "admin_pagination_states",
        title: "Все режимы",
        frame: "window",
        width: 860,
        render: () => <PaginationStates />,
      },
    ],
  },
  {
    id: "admin-search-picker",
    title: "Поиск и пикеры",
    description:
      "SearchInput: пауза 300 мс, крестик и Esc. Picker и PickerFilter ищут на сервере до 20 строк, при has_more просят уточнить.",
    entries: [
      {
        id: "admin_search_input",
        title: "Поле поиска: пусто и запрос идёт",
        frame: "window",
        width: 520,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <SearchDemo />
            <SearchDemo busy initial="Келлер" />
          </div>
        ),
      },
      {
        id: "admin_picker",
        title: "Пикер человека и фильтр организации",
        note: "Стрелки, Enter, Esc. Пустой запрос показывает первых по имени.",
        frame: "window",
        width: 560,
        render: () => <PickerDemo />,
      },
    ],
  },
  {
    id: "admin-no-results",
    title: "Ничего не найдено и пока пусто",
    description:
      "NoResults: условия отсекли всё, действие сбрасывает их. EmptyState: данных ещё нет, действие создаёт первое.",
    entries: [
      {
        id: "admin_no_results",
        title: "Два разных состояния",
        frame: "window",
        width: 560,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <NoResults framed query="келлер" onReset={() => undefined} />
            <EmptyState
              framed
              icon={<Users size={18} />}
              title="Людей пока нет"
              description="Пригласите первых участников."
              action={
                <button type="button" className="btn primary sm">
                  Пригласить
                </button>
              }
            />
          </div>
        ),
      },
      {
        id: "admin_active_filters",
        title: "Выбранные условия",
        frame: "window",
        width: 640,
        render: () => (
          <ActiveFilters
            total={1_204}
            onReset={() => undefined}
            items={[
              {
                id: "status",
                label: "Состояние",
                value: "Активен, Отключён",
                onRemove: () => undefined,
              },
              {
                id: "org",
                label: "Организация",
                value: "Студенты ФКН",
                onRemove: () => undefined,
              },
            ]}
          />
        ),
      },
    ],
  },
];
