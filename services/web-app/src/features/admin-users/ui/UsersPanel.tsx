import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Building2, Users } from "lucide-react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import {
  toast,
  useListQueryState,
  useServerList,
  type ListStateOptions,
} from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  FilterBar,
  FilterMenu,
  Modal,
  PersonCell,
  PickerFilter,
  SecretOnce,
  SortSelect,
  Spinner,
  usePickedItem,
  type ActiveFilter,
} from "@shared/ui";
import {
  adminPickers,
  useBootstrap,
  type AccountStatus,
  type AdminUser,
} from "@entities/session";
import { adminUsersApi } from "../api/adminUsersApi";
import {
  ACCOUNT_STATUSES,
  adminUsersKeys,
  useIssueResetLink,
  useRevokeSessions,
  useUser,
  useUserAction,
  useUserFacets,
} from "../api/adminUsersQueries";
import type { Failure } from "../lib/failure";
import { formatFull } from "../lib/format";
import { PersonDrawer } from "./PersonDrawer";
import { ACTION_ICON, userActions, type UserActionKind } from "./userActions";
import { AccountStatusLabel, FailureNotice, RoleLabel, When } from "./parts";

type Confirm = { user: AdminUser; kind: UserActionKind };

// Колонки не прыгают, когда поиск ничего не нашёл.
const COLUMN_WIDTHS = {
  status: 190,
  role: 160,
  projects: 92,
  last_login_at: 160,
  actions: 52,
};

const SORT_FIELDS = [
  "name",
  "email",
  "created_at",
  "last_login_at",
  "status",
] as const;
type UserSort = (typeof SORT_FIELDS)[number];
type UserFilter = "status" | "is_admin" | "org";

// Сортируют сервер и заголовки столбцов; дата регистрации и почта столбцов
// не имеют, их порядок выбирается списком «Порядок».
const LIST: ListStateOptions<UserFilter, UserSort> = {
  filters: {
    status: { multi: true, values: ACCOUNT_STATUSES },
    is_admin: { values: ["true", "false"] },
    org: {},
  },
  sort: { fields: SORT_FIELDS, default: "-created_at" },
};
const SORTABLE: readonly UserSort[] = ["name", "status", "last_login_at"];
const ORGS = adminPickers.orgs();

// Testid пунктов меню строки: их ждут тесты.
const MENU_TESTID: Record<UserActionKind, string> = {
  enable: "user-enable",
  disable: "user-disable",
  grantAdmin: "user-admin",
  revokeAdmin: "user-admin",
  resetLink: "user-reset",
  revokeSessions: "user-sessions",
  remove: "user-remove",
};

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

/** Вкладка «Люди»: поиск, фильтр по состоянию, карточка человека и действия над аккаунтом. */
export const UsersPanel = ({
  renderOrgs,
}: {
  renderOrgs?: ((user: AdminUser) => ReactNode) | undefined;
}) => {
  const { t, i18n } = useTranslation("adminUsers");
  const selfId = useBootstrap().data?.user?.id ?? "";
  const list = useListQueryState(LIST);
  const users = useServerList({
    state: list,
    queryKey: adminUsersKeys.usersList(),
    fetchPage: adminUsersApi.usersPage,
  });
  const facets = useUserFacets(list.q).data;
  const org = usePickedItem(ORGS, list.filter("org") || null, null);
  const act = useUserAction();
  const issue = useIssueResetLink();
  const revoke = useRevokeSessions();
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [link, setLink] = useState<{
    user: AdminUser;
    url: string;
    notified: boolean;
    expires: string;
  } | null>(null);
  // Открытая карточка живёт в адресе (?user=…): ссылка открывает её снова.
  const [params, setParams] = useSearchParams();
  const openId = params.get("user");
  const setOpenId = useCallback(
    (id: string | null) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (id) next.set("user", id);
          else next.delete("user");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const busy = act.isPending || issue.isPending || revoke.isPending;
  const rows = users.items;
  const row = rows.find((u) => u.id === openId) ?? null;
  // Карточка читает человека с сервера: после действия видно новое состояние,
  // даже если человек ушёл с текущей страницы.
  const person = useUser(openId, row);
  const opened = openId ? (person.data ?? row) : null;

  const pick = (user: AdminUser, kind: UserActionKind) => {
    setFailure(null);
    setConfirm({ user, kind });
  };

  const run = () => {
    if (!confirm) return;
    const { user, kind } = confirm;
    setFailure(null);
    const fail = (error: unknown) => {
      setFailure(asFailure(error));
      setConfirm(null);
    };
    if (kind === "resetLink") {
      issue.mutate(user.id, {
        onSuccess: (res) => {
          setLink({
            user,
            url: res.link,
            notified: res.user_notified,
            expires: res.expires_at,
          });
          setConfirm(null);
        },
        onError: fail,
      });
    } else if (kind === "revokeSessions") {
      revoke.mutate(user.id, {
        onSuccess: (count) => {
          toast.success(t("notice.sessions", { count, name: user.name }));
          setConfirm(null);
        },
        onError: fail,
      });
    } else {
      act.mutate(
        { kind, id: user.id },
        {
          onSuccess: () => {
            toast.success(t(`done.${kind}`, { name: user.name }));
            if (kind === "remove") setOpenId(null);
            setConfirm(null);
          },
          onError: fail,
        },
      );
    }
  };

  const columns = useMemo<ColumnDef<AdminUser>[]>(
    () => [
      {
        id: "name",
        header: t("users.columns.person"),
        cell: ({ row }) => (
          <PersonCell
            name={row.original.name}
            email={row.original.email}
            id={row.original.id}
            badges={
              row.original.id === selfId ? (
                <Badge variant="subtle">{t("users.you")}</Badge>
              ) : null
            }
          />
        ),
      },
      {
        id: "status",
        header: t("users.columns.status"),
        cell: ({ row }) => <AccountStatusLabel status={row.original.status} />,
      },
      {
        id: "role",
        header: t("users.columns.role"),
        cell: ({ row }) => (
          <RoleLabel isAdmin={row.original.is_instance_admin} />
        ),
      },
      {
        id: "projects",
        header: () => (
          <span className="ppl-num">{t("users.columns.projects")}</span>
        ),
        cell: ({ row }) => (
          <span
            className={
              row.original.project_count === 0 ? "ppl-num ppl-faint" : "ppl-num"
            }
          >
            {row.original.project_count}
          </span>
        ),
      },
      {
        id: "last_login_at",
        sortDescFirst: true,
        header: t("users.columns.lastLogin"),
        cell: ({ row }) => (
          <span className="ppl-muted">
            <When iso={row.original.last_login_at} empty={t("users.never")} />
          </span>
        ),
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("users.columns.actions")}</span>
        ),
        cell: ({ row }) => {
          const u = row.original;
          return (
            // Меню внутри кликабельной строки: клик и Enter по нему не открывают карточку.
            <div
              className="ppl-actions"
              onClick={(event) => {
                event.stopPropagation();
              }}
              onKeyDown={(event) => {
                event.stopPropagation();
              }}
            >
              <ActionMenu
                label={t("users.actions.open", { name: u.name })}
                testId={`user-actions-${u.id}`}
                items={userActions(u, u.id === selfId).map((a) => ({
                  id: a.kind,
                  label: t(`users.actions.${a.kind}`),
                  icon: ACTION_ICON[a.kind],
                  danger: a.danger,
                  disabled: a.disabled || busy,
                  testId: `${MENU_TESTID[a.kind]}-${u.id}`,
                  onSelect: () => {
                    pick(u, a.kind);
                  },
                }))}
              />
            </div>
          );
        },
      },
    ],
    [t, selfId, busy],
  );

  const danger = confirm?.kind === "remove" || confirm?.kind === "disable";
  const statuses = list.filters.status as readonly AccountStatus[];
  const role = list.filter("is_admin");
  const statusTotal = facets
    ? ACCOUNT_STATUSES.reduce((sum, s) => sum + (facets.status[s] ?? 0), 0)
    : null;

  const active: ActiveFilter[] = [
    ...(list.q
      ? [
          {
            id: "q",
            label: t("filters.search"),
            value: list.q,
            onRemove: () => {
              list.setQ("");
            },
          },
        ]
      : []),
    ...(statuses.length > 0
      ? [
          {
            id: "status",
            label: t("users.columns.status"),
            value: statuses.map((s) => t(`status.${s}`)).join(", "),
            onRemove: () => {
              list.setFilter("status", null);
            },
          },
        ]
      : []),
    ...(role
      ? [
          {
            id: "is_admin",
            label: t("users.columns.role"),
            value: t(role === "true" ? "filters.admins" : "filters.members"),
            onRemove: () => {
              list.setFilter("is_admin", null);
            },
          },
        ]
      : []),
    ...(list.filter("org")
      ? [
          {
            id: "org",
            label: t("filters.org"),
            value: org?.name ?? list.filter("org"),
            onRemove: () => {
              list.setFilter("org", null);
            },
          },
        ]
      : []),
  ];

  return (
    <div className="ppl-stack" data-testid="users-panel">
      <FilterBar
        search={list.q}
        onSearchChange={list.setQ}
        searchLabel={t("users.search")}
        searchPlaceholder={t("users.search")}
        busy={users.isFetching}
        onReset={list.reset}
        active={active}
        total={users.isLoading ? null : users.total}
        extra={
          <>
            <FilterMenu
              label={t("users.columns.status")}
              testId="users-filter-status"
              values={statuses}
              onChange={(values) => {
                list.setFilter("status", values);
              }}
              options={ACCOUNT_STATUSES.map((s) => ({
                value: s,
                label: t(`status.${s}`),
                ...(facets ? { count: facets.status[s] ?? 0 } : {}),
              }))}
            />
            <FilterMenu
              label={t("users.columns.role")}
              testId="users-filter-role"
              single
              values={role ? [role] : []}
              onChange={(values) => {
                list.setFilter("is_admin", values[0] ?? null);
              }}
              options={[
                {
                  value: "true",
                  label: t("filters.admins"),
                  ...(facets ? { count: facets.admins } : {}),
                },
                {
                  value: "false",
                  label: t("filters.members"),
                  ...(facets && statusTotal !== null
                    ? { count: Math.max(0, statusTotal - facets.admins) }
                    : {}),
                },
              ]}
            />
            <PickerFilter
              label={t("filters.org")}
              source={ORGS}
              icon={<Building2 size={13} aria-hidden="true" />}
              testId="users-filter-org"
              searchPlaceholder={t("filters.orgSearch")}
              value={list.filter("org") || null}
              onChange={(item) => {
                list.setFilter("org", item?.id ?? null);
              }}
            />
            <SortSelect
              sort={list.sort}
              onChange={list.setSort}
              testId="users-sort"
              label={t("sort.label")}
              options={[
                { field: "created_at", desc: true, label: t("sort.newest") },
                { field: "created_at", desc: false, label: t("sort.oldest") },
                { field: "name", desc: false, label: t("sort.name") },
                { field: "email", desc: false, label: t("sort.email") },
                {
                  field: "last_login_at",
                  desc: true,
                  label: t("sort.lastLogin"),
                },
              ]}
            />
          </>
        }
      />
      {failure && <FailureNotice failure={failure} />}
      <DataTable
        className="ppl-table"
        caption={t("users.caption")}
        columns={columns}
        data={rows}
        getRowId={(u) => u.id}
        loading={users.isFetching}
        error={users.isError ? t("users.loadFailed") : null}
        onRetry={() => {
          void users.refetch();
        }}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        sortable={SORTABLE}
        pagination={users.pagination}
        filtered={list.isFiltered}
        searchQuery={list.q}
        onResetFilters={list.reset}
        emptyTitle={t("users.empty.title")}
        emptyHint={t("users.empty.body")}
        emptyIcon={<Users size={18} />}
        columnWidths={COLUMN_WIDTHS}
        selectedRowId={openId}
        onRowClick={(u) => {
          setOpenId(u.id);
        }}
      />

      <PersonDrawer
        user={opened}
        renderOrgs={renderOrgs}
        self={opened?.id === selfId}
        busy={busy}
        onClose={() => {
          setOpenId(null);
        }}
        onAction={(kind) => {
          if (opened) pick(opened, kind);
        }}
      />

      <Modal
        isOpen={confirm !== null}
        onClose={() => {
          if (!busy) setConfirm(null);
        }}
        title={confirm ? t(`confirm.${confirm.kind}.title`) : undefined}
        description={
          confirm
            ? t(`confirm.${confirm.kind}.body`, { name: confirm.user.name })
            : undefined
        }
        footer={
          <>
            <Button
              variant="ghost"
              type="button"
              disabled={busy}
              onClick={() => {
                setConfirm(null);
              }}
            >
              {t("cancel")}
            </Button>
            <Button
              variant={danger ? "danger" : "primary"}
              type="button"
              disabled={busy}
              data-testid="user-confirm"
              onClick={run}
            >
              {busy && <Spinner size="sm" />}
              {confirm ? t(`confirm.${confirm.kind}.action`) : null}
            </Button>
          </>
        }
      />

      <Modal
        isOpen={link !== null}
        onClose={() => {
          setLink(null);
        }}
        title={t("resetLink.title")}
        description={
          link
            ? t("resetLink.lead", {
                name: link.user.name,
                time: formatFull(link.expires, i18n.language),
              })
            : undefined
        }
        width={520}
      >
        {link && (
          <div data-testid="link-delivery">
            <SecretOnce
              label={t("resetLink.label")}
              warning={t("linkOnce")}
              value={link.url}
              hint={
                link.notified ? t("resetLink.notified") : t("resetLink.manual")
              }
              onClose={() => {
                setLink(null);
              }}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};
