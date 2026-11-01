import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Building2, ChevronRight, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { localeTag, useListQueryState } from "@shared/lib";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FilterMenu,
  PageHeader,
  TableSkeleton,
  type ActiveFilter,
  type DataTablePagination,
} from "@shared/ui";
import type { AdminOrg } from "@entities/session";
import { ORGS_LIST, ORGS_SORTABLE } from "../lib/listState";
import { OrgMark, RoleBadge } from "./parts";

export type OrgsListViewProps = {
  status: "loading" | "error" | "ready";
  /** Строки текущей страницы: поиск, фильтр и сортировку сделал сервер. */
  orgs: readonly AdminOrg[];
  /** Админ установки: ему доступно создание организаций. */
  canCreate: boolean;
  onOpen: (slug: string) => void;
  onCreate: () => void;
  onRetry?: () => void;
  /** Сколько нашлось при текущих условиях; без него число не пишется. */
  total?: number | null;
  pagination?: DataTablePagination;
  /** Идёт запрос: старые строки остаются, поверх них крутилка. */
  fetching?: boolean;
};

/** Список организаций: поиск, фильтр, сортировка и страницы на сервере. */
export const OrgsListView = ({
  status,
  orgs,
  canCreate,
  onOpen,
  onCreate,
  onRetry,
  total = null,
  pagination,
  fetching = false,
}: OrgsListViewProps) => {
  const { t } = useTranslation("adminOrgs");
  // Состояние списка в адресе: тот же хук читает его и в загрузке (OrgsList).
  const list = useListQueryState(ORGS_LIST);
  const mine = list.filter("mine");

  const columns = useMemo<ColumnDef<AdminOrg>[]>(
    () => [
      {
        id: "name",
        header: t("list.columns.name"),
        cell: ({ row }) => (
          <span
            className="org-name"
            data-testid={`org-open-${row.original.slug}`}
          >
            <OrgMark name={row.original.name} slug={row.original.slug} />
            <span className="org-name-text">
              <span>{row.original.name}</span>
              <span className="org-slug">{row.original.slug}</span>
            </span>
          </span>
        ),
      },
      // Своя роль важна админу организации; админу установки она ничего не
      // говорит, ему колонка не нужна.
      ...(canCreate
        ? []
        : [
            {
              id: "role",
              header: t("list.columns.role"),
              enableSorting: false,
              cell: ({ row }) =>
                row.original.my_role ? (
                  <RoleBadge role={row.original.my_role} />
                ) : (
                  <span className="org-muted">{t("list.instanceAdmin")}</span>
                ),
            } satisfies ColumnDef<AdminOrg>,
          ]),
      {
        id: "member_count",
        sortDescFirst: true,
        header: () => (
          <span className="org-num">{t("list.columns.members")}</span>
        ),
        cell: ({ row }) => (
          <span className="org-num">
            {row.original.member_count.toLocaleString(localeTag())}
          </span>
        ),
      },
      {
        id: "project_count",
        sortDescFirst: true,
        header: () => (
          <span className="org-num">{t("list.columns.projects")}</span>
        ),
        cell: ({ row }) => (
          <span
            className={
              row.original.project_count === 0 ? "org-num org-faint" : "org-num"
            }
          >
            {row.original.project_count.toLocaleString(localeTag())}
          </span>
        ),
      },
      {
        id: "open",
        enableSorting: false,
        header: () => <span className="sr-only">{t("list.open")}</span>,
        cell: () => (
          <span className="org-chevron">
            <ChevronRight size={16} aria-hidden="true" />
          </span>
        ),
      },
    ],
    [t, canCreate],
  );

  const createButton = canCreate ? (
    <Button size="sm" type="button" onClick={onCreate} data-testid="org-create">
      <Plus size={14} aria-hidden="true" />
      {t("list.create")}
    </Button>
  ) : null;

  // «Пока пусто» только без условий: с поиском или фильтром это «ничего не найдено».
  const empty = status === "ready" && orgs.length === 0 && !list.isFiltered;
  const shown = status === "ready" && !empty;

  const active: ActiveFilter[] = [
    ...(list.q
      ? [
          {
            id: "q",
            label: t("list.filters.search"),
            value: list.q,
            onRemove: () => {
              list.setQ("");
            },
          },
        ]
      : []),
    ...(mine
      ? [
          {
            id: "mine",
            label: t("list.filters.mine"),
            value: t(
              mine === "true"
                ? "list.filters.member"
                : "list.filters.notMember",
            ),
            onRemove: () => {
              list.setFilter("mine", null);
            },
          },
        ]
      : []),
  ];

  return (
    <div className="org-page" data-testid="orgs-list">
      <PageHeader
        title={t("list.title")}
        description={canCreate ? t("list.leadAdmin") : t("list.leadOrgAdmin")}
        actions={shown ? createButton : null}
      />
      {status === "loading" && (
        <TableSkeleton rows={4} columns={4} withAvatar testId="orgs-loading" />
      )}
      {status === "error" && (
        <ErrorState framed title={t("list.loadFailed")} onRetry={onRetry} />
      )}
      {empty && (
        <EmptyState
          framed
          testId="orgs-empty"
          icon={<Building2 size={18} />}
          title={t("list.empty.title")}
          description={
            canCreate ? t("list.empty.bodyAdmin") : t("list.empty.bodyOrgAdmin")
          }
          action={createButton}
        />
      )}
      {shown && (
        <div className="org-stack">
          <FilterBar
            search={list.q}
            onSearchChange={list.setQ}
            searchLabel={t("list.search")}
            searchPlaceholder={t("list.search")}
            busy={fetching}
            onReset={list.reset}
            active={active}
            total={total}
            extra={
              // Админу организации видны только его организации: фильтр ему ни к чему.
              canCreate ? (
                <FilterMenu
                  label={t("list.filters.mine")}
                  testId="orgs-filter-mine"
                  single
                  values={mine ? [mine] : []}
                  onChange={(values) => {
                    list.setFilter("mine", values[0] ?? null);
                  }}
                  options={[
                    { value: "true", label: t("list.filters.member") },
                    { value: "false", label: t("list.filters.notMember") },
                  ]}
                />
              ) : null
            }
          />
          <DataTable
            className="org-table"
            caption={t("list.caption")}
            columns={columns}
            data={[...orgs]}
            getRowId={(o) => o.slug}
            loading={fetching}
            sorting={list.sorting}
            onSortingChange={list.onSortingChange}
            sortable={ORGS_SORTABLE}
            filtered={list.isFiltered}
            searchQuery={list.searchOnly}
            onResetFilters={list.reset}
            {...(pagination ? { pagination } : {})}
            onRowClick={(o) => {
              onOpen(o.slug);
            }}
          />
        </div>
      )}
    </div>
  );
};
