import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { RefreshCw, Send, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import {
  Badge,
  Button,
  DataTable,
  Input,
  LinkDelivery,
  Select,
  Spinner,
} from "@shared/ui";
import type { AdminInvitation } from "@entities/session";
import { PAGE_SIZE } from "../api/adminUsersApi";
import {
  useInvitations,
  useInvite,
  useResendInvite,
  useRevokeInvite,
} from "../api/adminUsersQueries";
import type { Failure } from "../lib/failure";
import { formatDate } from "../lib/format";
import { HINT } from "../lib/styles";
import { FailureNotice } from "./parts";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TTL_DAYS = [1, 3, 7, 14, 30] as const;

const STATUS_VARIANT = {
  pending: "info",
  used: "success",
  expired: "subtle",
} as const;

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

/** Вкладка «Приглашения»: создать ссылку, переслать, отозвать. Без почты ссылку показываем на экране. */
export const InvitationsPanel = () => {
  const { t, i18n } = useTranslation("adminUsers");
  const [page, setPage] = useState(0);
  const list = useInvitations(page);
  const invite = useInvite();
  const resend = useResendInvite();
  const revoke = useRevokeInvite();
  const [email, setEmail] = useState("");
  const [ttl, setTtl] = useState("7");
  const [tried, setTried] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [link, setLink] = useState<{
    url: string;
    email: string | null;
  } | null>(null);

  const busy = invite.isPending || resend.isPending || revoke.isPending;
  const trimmed = email.trim();
  const emailError =
    tried && trimmed !== "" && !EMAIL.test(trimmed)
      ? t("invitations.emailInvalid")
      : undefined;

  const shown = (created: { link: string | null }, to: string | null) => {
    setLink(created.link ? { url: created.link, email: to } : null);
  };

  const submit = () => {
    setTried(true);
    setFailure(null);
    if (trimmed !== "" && !EMAIL.test(trimmed)) return;
    invite.mutate(
      { email: trimmed === "" ? null : trimmed, ttl_days: Number(ttl) },
      {
        onSuccess: (created) => {
          shown(created, created.invitation.email);
          setEmail("");
          setTried(false);
        },
        onError: (error) => {
          setFailure(asFailure(error));
        },
      },
    );
  };

  const columns = useMemo<ColumnDef<AdminInvitation>[]>(
    () => [
      {
        id: "email",
        header: t("invitations.columns.email"),
        cell: ({ row }) =>
          row.original.email ?? (
            <span style={{ color: "var(--fg-2)" }}>
              {t("invitations.anyone")}
            </span>
          ),
      },
      {
        id: "status",
        header: t("invitations.columns.status"),
        cell: ({ row }) => (
          <Badge
            variant={STATUS_VARIANT[row.original.status]}
            data-testid={`invite-status-${row.original.id}`}
          >
            {t(`invitations.status.${row.original.status}`)}
          </Badge>
        ),
      },
      {
        id: "expires",
        header: t("invitations.columns.expires"),
        cell: ({ row }) => (
          <span style={{ color: "var(--fg-2)" }}>
            {row.original.used_at
              ? t("invitations.usedAt", {
                  date: formatDate(row.original.used_at, i18n.language),
                })
              : formatDate(row.original.expires_at, i18n.language)}
          </span>
        ),
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("invitations.columns.actions")}</span>
        ),
        cell: ({ row }) => {
          const inv = row.original;
          if (inv.status === "used") return null;
          return (
            <div
              className="flex"
              style={{ gap: 4, justifyContent: "flex-end" }}
            >
              <Button
                size="xs"
                variant="ghost"
                type="button"
                disabled={busy}
                data-testid={`invite-resend-${inv.id}`}
                onClick={() => {
                  setFailure(null);
                  resend.mutate(inv.id, {
                    onSuccess: (created) => {
                      shown(created, inv.email);
                    },
                    onError: (error) => {
                      setFailure(asFailure(error));
                    },
                  });
                }}
              >
                <RefreshCw size={13} aria-hidden="true" />
                {t("invitations.resend")}
              </Button>
              <Button
                size="xs"
                variant="ghost"
                type="button"
                disabled={busy}
                aria-label={t("invitations.revoke")}
                title={t("invitations.revoke")}
                data-testid={`invite-revoke-${inv.id}`}
                onClick={() => {
                  setFailure(null);
                  revoke.mutate(inv.id, {
                    onError: (error) => {
                      setFailure(asFailure(error));
                    },
                  });
                }}
              >
                <Trash2 size={13} aria-hidden="true" />
              </Button>
            </div>
          );
        },
      },
    ],
    [t, i18n.language, busy, resend, revoke],
  );

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="invitations-panel"
    >
      <form
        className="flex items-end"
        style={{ gap: 10, flexWrap: "wrap" }}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        data-testid="invite-form"
      >
        <div style={{ flex: "1 1 260px", minWidth: 220 }}>
          <Input
            label={t("invitations.email")}
            type="email"
            value={email}
            autoComplete="off"
            placeholder="name@example.org"
            {...(emailError ? { error: emailError } : {})}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
            data-testid="invite-email"
          />
        </div>
        <div className="field" style={{ width: 160 }}>
          <label htmlFor="invite-ttl">{t("invitations.ttl")}</label>
          <Select
            id="invite-ttl"
            value={ttl}
            placeholder={t("invitations.ttl")}
            options={TTL_DAYS.map((d) => ({
              value: String(d),
              label: t("invitations.days", { count: d }),
            }))}
            onValueChange={setTtl}
          />
        </div>
        <Button
          type="submit"
          disabled={busy}
          style={{ gap: 6 }}
          data-testid="invite-submit"
        >
          {invite.isPending ? (
            <Spinner size="sm" />
          ) : (
            <Send size={14} aria-hidden="true" />
          )}
          {t("invitations.create")}
        </Button>
      </form>
      <p className="hint" style={{ marginTop: -6 }}>
        {t("invitations.emailHint")}
      </p>
      {failure && <FailureNotice failure={failure} />}
      {link && (
        <div
          className="flex flex-col"
          style={{ gap: 8 }}
          data-testid="invite-link"
        >
          <LinkDelivery link={link.url} kind="invite" once />
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
        caption={t("invitations.caption")}
        columns={columns}
        data={list.data?.items ?? []}
        getRowId={(i) => i.id}
        loading={list.isPending}
        error={list.isError ? t("invitations.loadFailed") : null}
        onRetry={() => {
          void list.refetch();
        }}
        emptyTitle={t("invitations.empty.title")}
        emptyHint={t("invitations.empty.body")}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total: list.data?.total ?? 0,
          onPageChange: setPage,
        }}
      />
      <p style={HINT}>{t("invitations.note")}</p>
    </div>
  );
};
