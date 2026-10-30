import { useState } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import {
  HardDrive,
  KeyRound,
  Pause,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  Users,
} from "lucide-react";
import type { GalleryGroup } from "../../lib/stateGallery";
import { ActionMenu } from "../ActionMenu";
import { PageHeader, PageTabs } from "../AdminPage";
import { Badge } from "../Badge";
import { ConfirmByName } from "../ConfirmByName";
import { DataTable } from "../DataTable";
import { EmptyState, ErrorState } from "../EmptyState";
import { FilterBar } from "../FilterBar";
import { KpiGrid, KpiTile } from "../KpiTile";
import { PersonCell } from "../PersonCell";
import { SecretOnce } from "../SecretOnce";
import { ListRow, Section, SectionList, SettingRow } from "../Section";
import { StatusDot, type StatusDotStatus } from "../StatusDot";
import { StickySaveBar } from "../StickySaveBar";
import { TableSkeleton } from "../TableSkeleton";

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

const HeaderDemo = () => {
  const [tab, setTab] = useState<"runners" | "queue">("runners");
  return (
    <PageHeader
      title="Раннеры и очередь"
      description="Машины, которые выполняют сборки и проверки."
      actions={
        <button type="button" className="btn primary sm">
          <Plus size={13} aria-hidden="true" />
          Создать токен
        </button>
      }
      tabs={
        <PageTabs
          label="Вид"
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "runners", label: "Раннеры", count: 5 },
            { id: "queue", label: "Очередь", count: 3, countTone: "accent" },
          ]}
        />
      }
    />
  );
};

/** Форма настроек: строки, замок окружения и одна панель сохранения. */
const SettingsDemo = () => {
  const [name, setName] = useState("HSE Doc Studio");
  const [open, setOpen] = useState(false);
  const dirty = (name !== "HSE Doc Studio" ? 1 : 0) + (open ? 1 : 0);
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 420 }}>
      <Section
        title="Название и адрес"
        description="Название видно в письмах и заголовке окна."
      >
        <SettingRow
          label="Название установки"
          hint="Например, Студия кафедры."
          htmlFor="kit-name"
          align="stretch"
        >
          <input
            id="kit-name"
            className="input"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
        </SettingRow>
        <SettingRow
          label="Публичный адрес"
          hint="По нему открывают Студию."
          locked
          align="stretch"
        >
          <input
            className="input mono"
            value="https://studio.example.org"
            readOnly
            disabled
          />
        </SettingRow>
        <SettingRow label="Открытая регистрация" hint="Любой с почтой.">
          <input
            type="checkbox"
            checked={open}
            aria-label="Открытая регистрация"
            onChange={(e) => {
              setOpen(e.target.checked);
            }}
          />
        </SettingRow>
      </Section>
      <StickySaveBar
        dirtyCount={dirty}
        onSave={noop}
        onDiscard={() => {
          setName("HSE Doc Studio");
          setOpen(false);
        }}
      />
    </div>
  );
};

const KPIS = (
  <KpiGrid>
    <KpiTile
      label="Люди"
      icon={<Users size={14} aria-hidden="true" />}
      value="128"
      tone="warning"
      secondary="3 ждут одобрения"
    />
    <KpiTile
      label="Раннеры на связи"
      icon={<Server size={14} aria-hidden="true" />}
      value="4"
      unit="из 5"
      secondary="В очереди 2, выполняется 3"
      sparkline={[2, 3, 3, 5, 4, 6, 4, 3]}
    />
    <KpiTile
      label="Занято места"
      icon={<HardDrive size={14} aria-hidden="true" />}
      value="86 ГБ"
      progress={78}
      progressTone="warning"
      secondary="Свободно 24 ГБ из 110 ГБ"
    />
    <KpiTile
      label="Сервисы в норме"
      value="6"
      unit="из 6"
      tone="success"
      secondary="Всё работает"
    />
  </KpiGrid>
);

export const getAdminKitGallery = (): GalleryGroup[] => [
  {
    id: "admin-page-header",
    title: "Заголовок страницы",
    description:
      "PageHeader: h1, одна строка описания, действия справа, вкладки сразу под заголовком. Ширину задаёт PageContainer (wide 1120 / narrow 760).",
    entries: [
      {
        id: "admin_page_header",
        title: "С действием и вкладками",
        frame: "window",
        width: 760,
        render: () => <HeaderDemo />,
      },
    ],
  },
  {
    id: "admin-settings-section",
    title: "Раздел настроек и панель сохранения",
    description:
      "Section + SettingRow: подпись и пояснение слева, управление справа; на узкой карточке в столбец. Замок: значение задано окружением. StickySaveBar появляется при правках.",
    entries: [
      {
        id: "admin_settings_section",
        title: "Строки настроек",
        note: "Измените название или флажок: снизу появится панель сохранения.",
        frame: "window",
        width: 720,
        render: () => <SettingsDemo />,
      },
      {
        id: "admin_save_bar_busy",
        title: "Панель сохранения: идёт сохранение и ошибка",
        frame: "window",
        width: 720,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <StickySaveBar dirtyCount={2} busy onSave={noop} onDiscard={noop} />
            <StickySaveBar
              dirtyCount={1}
              error="Не удалось сохранить: сервер не ответил."
              onSave={noop}
              onDiscard={noop}
            />
          </div>
        ),
      },
    ],
  },
  {
    id: "admin-kpi",
    title: "Сводные плитки",
    description:
      "KpiTile: подпись, число с единицей, строка с точкой тона, полоса или спарклайн. С to плитка ведёт в раздел.",
    entries: [
      {
        id: "admin_kpi_ready",
        title: "Данные",
        frame: "window",
        width: 980,
        render: () => KPIS,
      },
      {
        id: "admin_kpi_states",
        title: "Загрузка и ошибка",
        frame: "window",
        width: 520,
        render: () => (
          <KpiGrid>
            <KpiTile label="Люди" value="" loading />
            <KpiTile label="Хранилище" value="" error="Не удалось загрузить" />
          </KpiGrid>
        ),
      },
    ],
  },
  {
    id: "admin-states",
    title: "Пусто, ошибка, загрузка",
    entries: [
      {
        id: "admin_empty_state",
        title: "Пустое состояние",
        frame: "window",
        width: 560,
        render: () => (
          <EmptyState
            framed
            icon={<KeyRound size={18} />}
            title="Токенов пока нет"
            description="Создайте токен и запустите раннер на своей машине."
            action={
              <button type="button" className="btn primary sm">
                Создать токен
              </button>
            }
          />
        ),
      },
      {
        id: "admin_error_state",
        title: "Ошибка с повтором, полная и в строку",
        frame: "window",
        width: 560,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <ErrorState
              framed
              description="Сервер не ответил. Проверьте соединение."
              onRetry={noop}
            />
            <ErrorState
              compact
              framed
              title="Журнал не загрузился"
              onRetry={noop}
            />
          </div>
        ),
      },
      {
        id: "admin_table_skeleton",
        title: "Скелет таблицы",
        frame: "window",
        width: 640,
        render: () => <TableSkeleton rows={4} columns={4} withAvatar />,
      },
    ],
  },
  {
    id: "admin-people",
    title: "Люди, метки, состояния",
    description:
      "PersonCell: аватар, имя, почта; без данных нейтральная подпись, id только в подсказке. Метки и состояния набраны sans.",
    entries: [
      {
        id: "admin_person_cell",
        title: "Человек в строке",
        frame: "window",
        width: 520,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <PersonCell
              id="u_01"
              name="Мария Келлер"
              email="maria.keller@example.org"
              badges={<Badge variant="accent">Администратор</Badge>}
            />
            <PersonCell id="u_02" email="new.student@example.org" />
            <PersonCell id="u_01hx7k9zz" />
            <PersonCell size="sm" id="u_03" name="Пётр Орлов" />
          </div>
        ),
      },
      {
        id: "admin_list_rows",
        title: "Строки списка в разделе",
        note: "ListRow: значок в тоне, текст, справа время или число; с to строка ведёт дальше.",
        frame: "window",
        width: 560,
        render: () => (
          <Section title="Требует внимания" flush>
            <SectionList>
              <ListRow
                icon={<Users size={15} />}
                tone="warning"
                title="2 человека ждут одобрения"
                description="Пока заявка не одобрена, человек не может войти."
                to="/admin/users"
              />
              <ListRow
                icon={<Server size={15} />}
                tone="danger"
                title="Ни один раннер не на связи"
                description="Сборки ждут в очереди."
                meta="5 мин"
              />
            </SectionList>
          </Section>
        ),
      },
      {
        id: "admin_badges",
        title: "Метки и точки состояния",
        frame: "window",
        width: 560,
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <Badge>Пользователь</Badge>
              <Badge variant="accent">Администратор</Badge>
              <Badge variant="success">Активен</Badge>
              <Badge variant="warning">Ждёт одобрения</Badge>
              <Badge variant="error">Отключён</Badge>
              <Badge variant="info">Задано окружением</Badge>
            </div>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              {(
                ["success", "warning", "danger", "neutral", "info"] as const
              ).map((s) => (
                <StatusDot key={s} status={s} />
              ))}
            </div>
          </div>
        ),
      },
      {
        id: "admin_action_menu",
        title: "Действия строки в «⋯»",
        note: "Опасные пункты отделены чертой и окрашены.",
        frame: "window",
        width: 420,
        render: () => (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <ActionMenu
              label="Действия с runner-1"
              items={[
                {
                  id: "pause",
                  label: "Поставить на паузу",
                  icon: <Pause size={14} />,
                  onSelect: noop,
                },
                {
                  id: "rotate",
                  label: "Новый токен",
                  icon: <RefreshCw size={14} />,
                  onSelect: noop,
                },
                {
                  id: "remove",
                  label: "Удалить",
                  icon: <Trash2 size={14} />,
                  danger: true,
                  onSelect: noop,
                },
              ]}
            />
          </div>
        ),
      },
    ],
  },
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
