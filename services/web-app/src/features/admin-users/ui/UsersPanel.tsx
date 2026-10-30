import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Ban,
  CircleCheck,
  KeyRound,
  LogOut,
  MoreHorizontal,
  ShieldCheck,
  ShieldOff,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import {
  Badge,
  Button,
  DataTable,
  FilterBar,
  LinkDelivery,
  Modal,
  Popover,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
  Spinner,
} from "@shared/ui";
import {
  useBootstrap,
  type AccountStatus,
  type AdminUser,
} from "@entities/session";
import { PAGE_SIZE } from "../api/adminUsersApi";
import {
  useIssueResetLink,
  useRevokeSessions,
  useUserAction,
  useUsers,
} from "../api/adminUsersQueries";
import type { Failure } from "../lib/failure";
import { formatDate } from "../lib/format";
import { HINT } from "../lib/styles";
import { FailureNotice, Person, StatusBadge } from "./parts";

type Pending =
  | { kind: "disable" | "enable" | "grantAdmin" | "revokeAdmin" | "remove" }
  | { kind: "resetLink" | "revokeSessions" };

type Confirm = { user: AdminUser } & Pending;

const STATUSES: readonly AccountStatus[] = [
  "active",
  "pending_verification",
  "pending_approval",
  "disabled",
];

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

const menuItem = {
  width: "100%",
  justifyContent: "flex-start",
  gap: 8,
} as const;

/** Вкладка «Люди»: поиск, фильтр по состоянию, действия над учётными записями. */
export const UsersPanel = () => {
  const { t, i18n } = useTranslation("adminUsers");
  const selfId = useBootstrap().data?.user?.id ?? "";
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<AccountStatus | "">("");
  const [page, setPage] = useState(0);
  const users = useUsers({ q: search.trim(), status, page });
  const act = useUserAction();
  const issue = useIssueResetLink();
  const revoke = useRevokeSessions();
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [link, setLink] = useState<{ user: AdminUser; url: string } | null>(
    null,
  );
  const [notice, setNotice] = useState<string | null>(null);

  const busy = act.isPending || issue.isPending || revoke.isPending;
  const total = users.data?.total ?? 0;
  const rows = users.data?.items ?? [];

  const run = () => {
    if (!confirm) return;
    const { user } = confirm;
    setFailure(null);
    setNotice(null);
    const fail = (error: unknown) => {
      setFailure(asFailure(error));
      setConfirm(null);
    };
    if (confirm.kind === "resetLink") {
      issue.mutate(user.id, {
        onSuccess: (res) => {
          setLink({ user, url: res.link });
          setConfirm(null);
        },
        onError: fail,
      });
    } else if (confirm.kind === "revokeSessions") {
      revoke.mutate(user.id, {
        onSuccess: (count) => {
          setNotice(t("notice.sessions", { count, name: user.name }));
          setConfirm(null);
        },
        onError: fail,
      });
    } else {
      act.mutate(
        { kind: confirm.kind, id: user.id },
        {
          onSuccess: () => {
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
          <Person
            name={row.original.name}
            email={row.original.email}
            badge={
              row.original.id === selfId ? (
                <Badge variant="subtle">{t("users.you")}</Badge>
              ) : undefined
            }
          />
        ),
      },
      {
        id: "status",
        header: t("users.columns.status"),
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        id: "role",
        header: t("users.columns.role"),
        cell: ({ row }) =>
          row.original.is_instance_admin ? (
            <Badge variant="accent">{t("users.admin")}</Badge>
          ) : (
            <span style={{ color: "var(--fg-2)" }}>{t("users.member")}</span>
          ),
      },
      {
        id: "projects",
        header: t("users.columns.projects"),
        cell: ({ row }) => row.original.project_count,
      },
      {
        id: "lastLogin",
        header: t("users.columns.lastLogin"),
        cell: ({ row }) => (
          <span style={{ color: "var(--fg-2)" }}>
            {row.original.last_login_at
              ? formatDate(row.original.last_login_at, i18n.language)
              : t("users.never")}
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
          const self = u.id === selfId;
          const pick = (p: Pending) => () => {
            setFailure(null);
            setConfirm({ user: u, ...p });
          };
          return (
            <div className="flex" style={{ justifyContent: "flex-end" }}>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    size="xs"
                    variant="ghost"
                    type="button"
                    disabled={busy}
                    aria-label={t("users.actions.open", { name: u.name })}
                    data-testid={`user-actions-${u.id}`}
                  >
                    <MoreHorizontal size={14} aria-hidden="true" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent
                  width={240}
                  aria-label={t("users.actions.menu", { name: u.name })}
                >
                  <div className="flex flex-col" style={{ padding: 4 }}>
                    {u.status === "disabled" ? (
                      <PopoverClose asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          type="button"
                          style={menuItem}
                          data-testid={`user-enable-${u.id}`}
                          onClick={pick({ kind: "enable" })}
                        >
                          <CircleCheck size={14} aria-hidden="true" />
                          {t("users.actions.enable")}
                        </Button>
                      </PopoverClose>
                    ) : (
                      <PopoverClose asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          type="button"
                          disabled={self}
                          title={self ? t("users.actions.selfHint") : undefined}
                          style={menuItem}
                          data-testid={`user-disable-${u.id}`}
                          onClick={pick({ kind: "disable" })}
                        >
                          <Ban size={14} aria-hidden="true" />
                          {t("users.actions.disable")}
                        </Button>
                      </PopoverClose>
                    )}
                    <PopoverClose asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        disabled={self && u.is_instance_admin}
                        title={
                          self && u.is_instance_admin
                            ? t("users.actions.selfHint")
                            : undefined
                        }
                        style={menuItem}
                        data-testid={`user-admin-${u.id}`}
                        onClick={pick({
                          kind: u.is_instance_admin
                            ? "revokeAdmin"
                            : "grantAdmin",
                        })}
                      >
                        {u.is_instance_admin ? (
                          <ShieldOff size={14} aria-hidden="true" />
                        ) : (
                          <ShieldCheck size={14} aria-hidden="true" />
                        )}
                        {u.is_instance_admin
                          ? t("users.actions.revokeAdmin")
                          : t("users.actions.grantAdmin")}
                      </Button>
                    </PopoverClose>
                    <PopoverClose asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        style={menuItem}
                        data-testid={`user-reset-${u.id}`}
                        onClick={pick({ kind: "resetLink" })}
                      >
                        <KeyRound size={14} aria-hidden="true" />
                        {t("users.actions.resetLink")}
                      </Button>
                    </PopoverClose>
                    <PopoverClose asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        style={menuItem}
                        data-testid={`user-sessions-${u.id}`}
                        onClick={pick({ kind: "revokeSessions" })}
                      >
                        <LogOut size={14} aria-hidden="true" />
                        {t("users.actions.revokeSessions")}
                      </Button>
                    </PopoverClose>
                    {u.status === "disabled" && (
                      <PopoverClose asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          type="button"
                          style={{ ...menuItem, color: "var(--c-err)" }}
                          data-testid={`user-remove-${u.id}`}
                          onClick={pick({ kind: "remove" })}
                        >
                          <Trash2 size={14} aria-hidden="true" />
                          {t("users.actions.remove")}
                        </Button>
                      </PopoverClose>
                    )}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          );
        },
      },
    ],
    [t, i18n.language, selfId, busy],
  );

  const filtering = search.trim() !== "" || status !== "";
  const danger = confirm?.kind === "remove" || confirm?.kind === "disable";

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="users-panel"
    >
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
            options: STATUSES.map((s) => ({
              value: s,
              label: t(`status.${s}`),
            })),
          },
        ]}
        onReset={() => {
          setSearch("");
          setStatus("");
          setPage(0);
        }}
      />
      {failure && <FailureNotice failure={failure} />}
      {notice && (
        <p style={HINT} role="status" data-testid="users-notice">
          {notice}
        </p>
      )}
      {link && (
        <div className="flex flex-col" style={{ gap: 8 }}>
          <LinkDelivery link={link.url} kind="reset" once />
          <div>
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={() => {
                setLink(null);
              }}
            >
              {t("close")}
            </Button>
          </div>
        </div>
      )}
      <DataTable
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
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total,
          onPageChange: setPage,
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
    </div>
  );
};
