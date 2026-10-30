import { useMemo, useState } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { Building2, ChevronRight, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  PageHeader,
  TableSkeleton,
} from "@shared/ui";
import type { AdminOrg } from "@entities/session";
import { OrgMark, RoleBadge } from "./parts";

export type OrgsListViewProps = {
  status: "loading" | "error" | "ready";
  orgs: readonly AdminOrg[];
  /** Админ установки: ему доступно создание организаций. */
  canCreate: boolean;
  onOpen: (slug: string) => void;
  onCreate: () => void;
  onRetry?: () => void;
};

const compare = (a: AdminOrg, b: AdminOrg, key: string): number => {
  if (key === "members") return a.member_count - b.member_count;
  if (key === "projects") return a.project_count - b.project_count;
  return a.name.localeCompare(b.name);
};

/** Список организаций: поиск, сортировка, пустое состояние и ошибка загрузки. */
export const OrgsListView = ({
  status,
  orgs,
  canCreate,
  onOpen,
  onCreate,
  onRetry,
}: OrgsListViewProps) => {
  const { t } = useTranslation("adminOrgs");
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const found = needle
      ? orgs.filter(
          (o) =>
            o.name.toLowerCase().includes(needle) ||
            o.slug.toLowerCase().includes(needle),
        )
      : [...orgs];
    const first = sorting[0];
    if (!first) return found;
    return found.sort((a, b) =>
      first.desc ? -compare(a, b, first.id) : compare(a, b, first.id),
    );
  }, [orgs, search, sorting]);

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
        id: "members",
        header: () => (
          <span className="org-num">{t("list.columns.members")}</span>
        ),
        cell: ({ row }) => (
          <span className="org-num">{row.original.member_count}</span>
        ),
      },
      {
        id: "projects",
        header: () => (
          <span className="org-num">{t("list.columns.projects")}</span>
        ),
        cell: ({ row }) => (
          <span
            className={
              row.original.project_count === 0 ? "org-num org-faint" : "org-num"
            }
          >
            {row.original.project_count}
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

  const totals = useMemo(
    () => ({
      members: orgs.reduce((sum, o) => sum + o.member_count, 0),
      projects: orgs.reduce((sum, o) => sum + o.project_count, 0),
    }),
    [orgs],
  );

  const createButton = canCreate ? (
    <Button size="sm" type="button" onClick={onCreate} data-testid="org-create">
      <Plus size={14} aria-hidden="true" />
      {t("list.create")}
    </Button>
  ) : null;

  const empty = status === "ready" && orgs.length === 0;

  return (
    <div className="org-page" data-testid="orgs-list">
      <PageHeader
        title={t("list.title")}
        description={canCreate ? t("list.leadAdmin") : t("list.leadOrgAdmin")}
        actions={status === "ready" && orgs.length > 0 ? createButton : null}
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
      {status === "ready" && orgs.length > 0 && (
        <div className="org-stack">
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchLabel={t("list.search")}
            searchPlaceholder={t("list.search")}
            onReset={() => {
              setSearch("");
            }}
          />
          <DataTable
            className="org-table"
            caption={t("list.caption")}
            columns={columns}
            data={rows}
            getRowId={(o) => o.slug}
            emptyTitle={t("list.noMatch.title")}
            emptyHint={t("list.noMatch.body")}
            sorting={sorting}
            onSortingChange={setSorting}
            onRowClick={(o) => {
              onOpen(o.slug);
            }}
          />
          <p className="org-summary" data-testid="orgs-summary">
            {t("list.summary.orgs", { count: orgs.length })}
            <span className="adm-dotsep" />
            {t("list.summary.members", { count: totals.members })}
            <span className="adm-dotsep" />
            {t("list.summary.projects", { count: totals.projects })}
          </p>
        </div>
      )}
    </div>
  );
};
