import { forwardRef, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Link2, Mail, MailCheck, RefreshCw, Send, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import {
  ActionMenu,
  Button,
  DataTable,
  Input,
  Section,
  SecretOnce,
  Select,
  Spinner,
  StatusDot,
  type StatusDotStatus,
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
import { FailureNotice, When } from "./parts";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TTL_DAYS = [1, 3, 7, 14, 30] as const;

const STATUS_TONE: Record<AdminInvitation["status"], StatusDotStatus> = {
  pending: "info",
  used: "success",
  expired: "neutral",
};

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

type Shown =
  | { kind: "link"; url: string; email: string | null }
  | { kind: "sent"; email: string };

/**
 * Вкладка «Приглашения»: создать, переслать, отозвать. Ссылку показываем один
 * раз; если сервер отправил письмо сам, говорим об этом.
 */
export const InvitationsPanel = forwardRef<HTMLInputElement>(
  function InvitationsPanel(_props, emailRef) {
    const { t } = useTranslation("adminUsers");
    const [page, setPage] = useState(0);
    const list = useInvitations(page);
    const invite = useInvite();
    const resend = useResendInvite();
    const revoke = useRevokeInvite();
    const [email, setEmail] = useState("");
    const [ttl, setTtl] = useState("7");
    const [tried, setTried] = useState(false);
    const [failure, setFailure] = useState<Failure | null>(null);
    const [shown, setShown] = useState<Shown | null>(null);

    const busy = invite.isPending || resend.isPending || revoke.isPending;
    const trimmed = email.trim();
    const emailError =
      tried && trimmed !== "" && !EMAIL.test(trimmed)
        ? t("invitations.emailInvalid")
        : undefined;

    const show = (created: { link: string | null }, to: string | null) => {
      if (created.link)
        setShown({ kind: "link", url: created.link, email: to });
      else if (to) setShown({ kind: "sent", email: to });
      else setShown(null);
    };

    const submit = () => {
      setTried(true);
      setFailure(null);
      if (trimmed !== "" && !EMAIL.test(trimmed)) return;
      invite.mutate(
        { email: trimmed === "" ? null : trimmed, ttl_days: Number(ttl) },
        {
          onSuccess: (created) => {
            show(created, created.invitation.email);
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
          cell: ({ row }) => {
            const inv = row.original;
            return (
              <span className="ppl-target">
                <span className="ppl-target-icon" aria-hidden="true">
                  {inv.email ? <Mail size={14} /> : <Link2 size={14} />}
                </span>
                <span className="ppl-target-text">
                  <span>{inv.email ?? t("invitations.anyone")}</span>
                  {!inv.email && <span>{t("invitations.anyoneHint")}</span>}
                </span>
              </span>
            );
          },
        },
        {
          id: "status",
          header: t("invitations.columns.status"),
          cell: ({ row }) => (
            <span data-testid={`invite-status-${row.original.id}`}>
              <StatusDot
                status={STATUS_TONE[row.original.status]}
                label={t(`invitations.status.${row.original.status}`)}
              />
            </span>
          ),
        },
        {
          id: "expires",
          header: t("invitations.columns.expires"),
          cell: ({ row }) => {
            const inv = row.original;
            return (
              <span className="ppl-muted ppl-nowrap">
                {inv.status === "used" && inv.used_at ? (
                  <>
                    {t("invitations.when.used")} <When iso={inv.used_at} />
                  </>
                ) : inv.status === "expired" ? (
                  <>
                    {t("invitations.when.expired")}{" "}
                    <When iso={inv.expires_at} />
                  </>
                ) : (
                  <>
                    {t("invitations.when.pending")}{" "}
                    <When iso={inv.expires_at} future />
                  </>
                )}
              </span>
            );
          },
        },
        {
          id: "actions",
          header: () => (
            <span className="sr-only">{t("invitations.columns.actions")}</span>
          ),
          cell: ({ row }) => {
            const inv = row.original;
            if (inv.status === "used") return null;
            const target = inv.email ?? t("invitations.anyone");
            return (
              <div className="ppl-actions">
                <ActionMenu
                  label={t("invitations.menu", { target })}
                  testId={`invite-actions-${inv.id}`}
                  items={[
                    {
                      id: "resend",
                      label: t("invitations.resend"),
                      icon: <RefreshCw size={15} aria-hidden="true" />,
                      disabled: busy,
                      testId: `invite-resend-${inv.id}`,
                      onSelect: () => {
                        setFailure(null);
                        resend.mutate(inv.id, {
                          onSuccess: (created) => {
                            show(created, inv.email);
                          },
                          onError: (error) => {
                            setFailure(asFailure(error));
                          },
                        });
                      },
                    },
                    {
                      id: "revoke",
                      label: t("invitations.revoke"),
                      icon: <Trash2 size={15} aria-hidden="true" />,
                      danger: true,
                      disabled: busy,
                      testId: `invite-revoke-${inv.id}`,
                      onSelect: () => {
                        setFailure(null);
                        revoke.mutate(inv.id, {
                          onSuccess: () => {
                            toast.success(t("invitations.revoked"));
                          },
                          onError: (error) => {
                            setFailure(asFailure(error));
                          },
                        });
                      },
                    },
                  ]}
                />
              </div>
            );
          },
        },
      ],
      [t, busy, resend, revoke],
    );

    return (
      <div className="ppl-stack" data-testid="invitations-panel">
        <Section
          title={t("invitations.newTitle")}
          description={t("invitations.newLead")}
          testId="invite-section"
        >
          <form
            className="ppl-invite-form"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
            data-testid="invite-form"
          >
            <div className="ppl-invite-email">
              <Input
                ref={emailRef}
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
            <div className="field ppl-invite-ttl">
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
            <div className="ppl-invite-submit">
              <Button type="submit" disabled={busy} data-testid="invite-submit">
                {invite.isPending ? (
                  <Spinner size="sm" />
                ) : (
                  <Send size={14} aria-hidden="true" />
                )}
                {t("invitations.create")}
              </Button>
            </div>
          </form>
          {failure && (
            <div style={{ marginTop: 12 }}>
              <FailureNotice failure={failure} />
            </div>
          )}
          {shown?.kind === "link" && (
            <div
              style={{ marginTop: 16 }}
              data-testid="invite-link"
              className="ppl-reveal"
            >
              <div data-testid="link-delivery">
                <SecretOnce
                  label={t("invitations.linkLabel")}
                  warning={t("linkOnce")}
                  value={shown.url}
                  hint={
                    shown.email
                      ? t("invitations.linkFor", { email: shown.email })
                      : t("invitations.linkAnyone")
                  }
                  onClose={() => {
                    setShown(null);
                  }}
                />
              </div>
            </div>
          )}
          {shown?.kind === "sent" && (
            <p
              className="flex items-center ppl-muted"
              style={{ gap: 8, margin: "14px 0 0", fontSize: 12.5 }}
              role="status"
              data-testid="invite-sent"
            >
              <MailCheck
                size={15}
                aria-hidden="true"
                style={{ color: "var(--c-ok)" }}
              />
              {t("invitations.sent", { email: shown.email })}
            </p>
          )}
        </Section>

        <DataTable
          className="ppl-table"
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
          {...((list.data?.total ?? 0) > PAGE_SIZE
            ? {
                pagination: {
                  page,
                  pageSize: PAGE_SIZE,
                  total: list.data?.total ?? 0,
                  onPageChange: setPage,
                },
              }
            : {})}
        />
      </div>
    );
  },
);
