import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useBootstrap, type ChangeEmailResponse } from "@entities/session";
import { AccountValidationFailed } from "../api/accountApi";
import {
  useAccount,
  useAccountSessions,
  useChangeEmail,
  useChangePassword,
  useRevokeOtherSessions,
  useRevokeSession,
  useUpdateAccount,
} from "../api/accountQueries";
import type { Failure } from "../lib/failure";
import { CommitIdentityCard } from "./CommitIdentityCard";
import { PasswordCard } from "./PasswordCard";
import { ProfileCard } from "./ProfileCard";
import { SessionsCard } from "./SessionsCard";

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

/**
 * Раздел настроек «Аккаунт» серверного режима: имя и почта, пароль, подпись
 * версий и активные сессии. Тексты и поля те же, что отдаёт /api/v1/account.
 */
export const AccountSection = () => {
  const { t } = useTranslation("account");
  const bootstrap = useBootstrap().data;
  const account = useAccount();
  const sessions = useAccountSessions();
  const update = useUpdateAccount();
  const commit = useUpdateAccount();
  const password = useChangePassword();
  const email = useChangeEmail();
  const revoke = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();
  const [nameSaved, setNameSaved] = useState(false);
  const [commitSaved, setCommitSaved] = useState(false);
  const [passwordDone, setPasswordDone] = useState(false);
  // Новая форма после успеха: поля пустые, при ошибке остаются как были.
  const [passwordRound, setPasswordRound] = useState(0);
  const [emailResult, setEmailResult] = useState<ChangeEmailResponse | null>(
    null,
  );
  const [sessionFailure, setSessionFailure] = useState<Failure | null>(null);

  const profile = account.data;
  const issueOf = (error: unknown, field: string): string | undefined =>
    error instanceof AccountValidationFailed
      ? error.issues.find((i) => i.field === field)?.message
      : undefined;

  return (
    <>
      <div className="flex flex-col" style={{ gap: 4, marginBottom: 4 }}>
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          {t("section.title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("section.subtitle")}
        </p>
      </div>

      <div
        className="flex flex-col"
        style={{ gap: 14, paddingBottom: 14, maxWidth: 560 }}
      >
        {account.isLoading && (
          <div
            className="flex items-center"
            style={{ gap: 8, fontSize: 12 }}
            data-testid="account-loading"
          >
            <Spinner size="sm" />
            <span className="dim">{t("section.loading")}</span>
          </div>
        )}

        {account.isError && !profile && (
          <Notice
            tone="err"
            role="alert"
            text={t("section.loadFailed")}
            action={
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  void account.refetch();
                }}
              >
                {t("section.retry")}
              </button>
            }
          />
        )}

        {profile && (
          <>
            <ProfileCard
              profile={profile}
              emailVerified={bootstrap?.user?.email_verified ?? true}
              pending={update.isPending}
              nameIssue={issueOf(update.error, "name") ?? null}
              failure={
                update.isError &&
                !(update.error instanceof AccountValidationFailed)
                  ? asFailure(update.error)
                  : null
              }
              saved={nameSaved}
              onSave={(name) => {
                setNameSaved(false);
                update.mutate(
                  { name },
                  {
                    onSuccess: () => {
                      setNameSaved(true);
                    },
                  },
                );
              }}
              email={{
                pending: email.isPending,
                failure: email.isError ? asFailure(email.error) : null,
                result: emailResult,
                onSubmit: (input) => {
                  setEmailResult(null);
                  email.mutate(input, {
                    onSuccess: (result) => {
                      setEmailResult(result);
                    },
                  });
                },
              }}
            />
            <PasswordCard
              key={passwordRound}
              minLength={bootstrap?.auth.password_min_length ?? 10}
              passwordEnabled={bootstrap?.auth.password_enabled ?? true}
              pending={password.isPending}
              failure={password.isError ? asFailure(password.error) : null}
              done={passwordDone}
              onSubmit={({ current, next, signOutOthers }) => {
                setPasswordDone(false);
                password.mutate(
                  {
                    current_password: current,
                    new_password: next,
                    sign_out_other_sessions: signOutOthers,
                  },
                  {
                    onSuccess: () => {
                      setPasswordDone(true);
                      setPasswordRound((n) => n + 1);
                    },
                  },
                );
              }}
            />
            <CommitIdentityCard
              profile={profile}
              pending={commit.isPending}
              issues={{
                ...optional(
                  "commit_name",
                  issueOf(commit.error, "commit_name"),
                ),
                ...optional(
                  "commit_email",
                  issueOf(commit.error, "commit_email"),
                ),
              }}
              failure={
                commit.isError &&
                !(commit.error instanceof AccountValidationFailed)
                  ? asFailure(commit.error)
                  : null
              }
              saved={commitSaved}
              onSave={(patch) => {
                setCommitSaved(false);
                commit.mutate(patch, {
                  onSuccess: () => {
                    setCommitSaved(true);
                    toast.success(t("commit.toast"));
                  },
                });
              }}
            />
          </>
        )}

        <SessionsCard
          status={
            sessions.isError && !sessions.data
              ? "error"
              : sessions.data
                ? "ready"
                : "loading"
          }
          sessions={sessions.data ?? []}
          revokingId={revoke.isPending ? revoke.variables : null}
          revokingOthers={revokeOthers.isPending}
          failure={sessionFailure}
          onRetry={() => {
            void sessions.refetch();
          }}
          onRevoke={(id) => {
            setSessionFailure(null);
            revoke.mutate(id, {
              onError: (error) => {
                setSessionFailure(asFailure(error));
              },
            });
          }}
          onRevokeOthers={() => {
            setSessionFailure(null);
            revokeOthers.mutate(undefined, {
              onSuccess: () => {
                toast.success(t("sessions.toastOthers"));
              },
              onError: (error) => {
                setSessionFailure(asFailure(error));
              },
            });
          }}
        />
      </div>
    </>
  );
};

const optional = <K extends string>(
  key: K,
  value: string | undefined,
): Partial<Record<K, string>> =>
  value === undefined ? {} : ({ [key]: value } as Record<K, string>);
