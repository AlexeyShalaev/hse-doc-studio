import { useMemo, useState, type ReactNode } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { SearchX, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  FilterBar,
  Modal,
  PersonCell,
  SecretOnce,
  Spinner,
} from "@shared/ui";
import {
  useBootstrap,
  type AccountStatus,
  type AdminUser,
} from "@entities/session";
import { PAGE_SIZE } from "../api/adminUsersApi";
import {
  ACCOUNT_STATUSES,
  useIssueResetLink,
  useRevokeSessions,
  useStatusCounts,
  useUserAction,
  useUsers,
} from "../api/adminUsersQueries";
import type { Failure } from "../lib/failure";
import { formatFull } from "../lib/format";
import { PersonDrawer } from "./PersonDrawer";
import { ACTION_ICON, userActions, type UserActionKind } from "./userActions";
import { AccountStatusLabel, FailureNotice, RoleLabel, When } from "./parts";

type Confirm = { user: AdminUser; kind: UserActionKind };

// Колонки не прыгают, когда поиск ничего не нашёл.
const COLUMN_WIDTHS = {
  status: 200,
  role: 170,
  projects: 96,
  lastLogin: 170,
  actions: 52,
};

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
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<AccountStatus | "">("");
  const [page, setPage] = useState(0);
  const query = search.trim();
  const users = useUsers({ q: query, status, page });
  const counts = useStatusCounts(query);
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
  const [openId, setOpenId] = useState<string | null>(null);

  const busy = act.isPending || issue.isPending || revoke.isPending;
  const total = users.data?.total ?? 0;
  const rows = useMemo(() => users.data?.items ?? [], [users.data]);
  // Карточка берёт свежую запись из списка: после действия видно новое состояние.
  const opened = rows.find((u) => u.id === openId) ?? null;

  const pick = (user: AdminUser, kind: UserActionKind) => {
    setFailure(null);
    setConfirm({ user, kind });
  };

  const resetFilters = () => {
    setSearch("");
    setStatus("");
    setPage(0);
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
        id: "person",
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
        id: "lastLogin",
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

  const filtering = query !== "" || status !== "";
  const danger = confirm?.kind === "remove" || confirm?.kind === "disable";

  return (
    <div className="ppl-stack" data-testid="users-panel">
      <FilterBar
        search={search}
        onSearchChange={(value) => {
          setSearch(value);
          setPage(0);
        }}
        searchLabel={t("users.search")}
        searchPlaceholder={t("users.search")}
        filters={[
          {
            id: "status",
            label: t("users.columns.status"),
            value: status,
            onChange: (value) => {
              setStatus(value as AccountStatus | "");
              setPage(0);
            },
            options: ACCOUNT_STATUSES.map((s) => ({
              value: s,
              label: t(`status.${s}`),
              ...(counts[s] !== undefined ? { count: counts[s] } : {}),
            })),
          },
        ]}
        onReset={resetFilters}
      />
      {failure && <FailureNotice failure={failure} />}
      <DataTable
        className="ppl-table"
        caption={t("users.caption")}
        columns={columns}
        data={rows}
        getRowId={(u) => u.id}
        loading={users.isPending}
        error={users.isError ? t("users.loadFailed") : null}
        onRetry={() => {
          void users.refetch();
        }}
        emptyTitle={
          filtering ? t("users.noMatch.title") : t("users.empty.title")
        }
        emptyHint={filtering ? t("users.noMatch.body") : t("users.empty.body")}
        emptyIcon={filtering ? <SearchX size={18} /> : <Users size={18} />}
        columnWidths={COLUMN_WIDTHS}
        emptyAction={
          filtering ? (
            <Button
              size="sm"
              variant="secondary"
              type="button"
              onClick={resetFilters}
            >
              {t("users.noMatch.reset")}
            </Button>
          ) : null
        }
        selectedRowId={openId}
        onRowClick={(u) => {
          setOpenId(u.id);
        }}
        {...(total > PAGE_SIZE
          ? {
              pagination: {
                page,
                pageSize: PAGE_SIZE,
                total,
                onPageChange: setPage,
              },
            }
          : {})}
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
