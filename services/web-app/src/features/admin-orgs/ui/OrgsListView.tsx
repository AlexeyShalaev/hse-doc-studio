import { useMemo, useState } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, DataTable, FilterBar, PageHeader } from "@shared/ui";
import type { AdminOrg } from "@entities/session";
import { RoleBadge } from "./parts";

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
            data-testid={`org-open-${row.original.slug}`}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 1,
              minWidth: 0,
            }}
          >
            <span style={{ fontWeight: 600, fontSize: 13 }}>
              {row.original.name}
            </span>
            <span
              className="mono"
              style={{ fontSize: 11, color: "var(--fg-2)" }}
            >
              {row.original.slug}
            </span>
          </span>
        ),
      },
      {
        id: "role",
        header: t("list.columns.role"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.my_role ? (
            <RoleBadge role={row.original.my_role} />
          ) : (
            <Badge variant="subtle">{t("list.instanceAdmin")}</Badge>
          ),
      },
      {
        id: "members",
        header: t("list.columns.members"),
        cell: ({ row }) => row.original.member_count,
      },
      {
        id: "projects",
        header: t("list.columns.projects"),
        cell: ({ row }) => row.original.project_count,
      },
    ],
    [t],
  );

  const createButton = canCreate ? (
    <Button
      size="sm"
      type="button"
      onClick={onCreate}
      style={{ gap: 6 }}
      data-testid="org-create"
    >
      <Plus size={14} aria-hidden="true" />
      {t("list.create")}
    </Button>
  ) : null;

  const searching = search.trim() !== "";

  return (
    <div className="flex flex-col" style={{ gap: 14 }} data-testid="orgs-list">
      <PageHeader
        title={t("list.title")}
        description={canCreate ? t("list.leadAdmin") : t("list.leadOrgAdmin")}
        actions={status === "ready" && orgs.length > 0 ? createButton : null}
      />
      {status === "ready" && orgs.length > 0 && (
        <FilterBar
          search={search}
          onSearchChange={setSearch}
          searchLabel={t("list.search")}
          searchPlaceholder={t("list.search")}
          onReset={() => {
            setSearch("");
          }}
        />
      )}
      <DataTable
        caption={t("list.caption")}
        columns={columns}
        data={rows}
        getRowId={(o) => o.slug}
        loading={status === "loading"}
        error={status === "error" ? t("list.loadFailed") : null}
        {...(onRetry ? { onRetry } : {})}
        emptyTitle={searching ? t("list.noMatch.title") : t("list.empty.title")}
        emptyHint={
          searching
            ? t("list.noMatch.body")
            : canCreate
              ? t("list.empty.bodyAdmin")
              : t("list.empty.bodyOrgAdmin")
        }
        emptyAction={searching ? null : createButton}
        sorting={sorting}
        onSortingChange={setSorting}
        onRowClick={(o) => {
          onOpen(o.slug);
        }}
      />
    </div>
  );
};
