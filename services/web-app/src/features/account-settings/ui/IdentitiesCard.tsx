import { useState } from "react";
import { KeyRound, Link2, Unlink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS, HINT } from "../lib/styles";
import type { IdentityRow } from "../lib/identityRows";
import { AccountCard } from "./parts";

export type IdentityProvider = { id: string; label: string };

export type IdentitiesCardProps = {
  status: "loading" | "error" | "ready";
  identities?: IdentityRow[];
  /** Провайдеры, настроенные на установке: из них предлагаем привязать недостающие. */
  providers?: IdentityProvider[];
  /** Провайдер, к которому уходим сейчас. */
  linkingId?: string | null;
  /** Привязка, которую отвязывают сейчас. */
  unlinkingId?: string | null;
  failure?: Failure | null;
  onRetry?: () => void;
  onLink: (providerId: string) => void;
  onUnlink: (id: string) => void;
};

/** Способы входа в аккаунт: пароль и привязанные внешние провайдеры. Последний способ не снимается. */
export const IdentitiesCard = ({
  status,
  identities = [],
  providers = [],
  linkingId = null,
  unlinkingId = null,
  failure = null,
  onRetry,
  onLink,
  onUnlink,
}: IdentitiesCardProps) => {
  const { t } = useTranslation("account");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const linked = new Set(identities.map((i) => i.provider_id));
  const free = providers.filter((p) => !linked.has(p.id));
  const sole = identities.length === 1;

  return (
    <AccountCard
      id="account-identities"
      title={t("identities.title")}
      sub={t("identities.sub")}
      testId="account-identities"
    >
      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="identities-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("identities.loading")}</span>
        </div>
      )}

      {status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("identities.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("identities.retry")}
              </button>
            )
          }
        />
      )}

      {status === "ready" && (
        <>
          <ul
            style={{ listStyle: "none", margin: 0, padding: 0 }}
            className="flex flex-col"
            data-testid="identities-list"
          >
            {identities.map((identity) => {
              const password = identity.kind === "password";
              const Icon = password ? KeyRound : Link2;
              const busy = unlinkingId === identity.id;
              const title = password
                ? t("identities.password")
                : identity.provider_label;
              return (
                <li
                  key={identity.id}
                  data-testid={`identity-${identity.id}`}
                  className="flex items-center"
                  style={{
                    gap: 12,
                    padding: "10px 0",
                    borderBottom: "1px dashed var(--border)",
                  }}
                >
                  <Icon
                    size={18}
                    aria-hidden="true"
                    style={{ color: "var(--fg-2)", flexShrink: 0 }}
                  />
                  <div
                    className="flex flex-col"
                    style={{ gap: 2, flex: 1, minWidth: 0 }}
                  >
                    <span
                      className="flex items-center"
                      style={{
                        gap: 8,
                        fontSize: 13,
                        fontWeight: 500,
                        flexWrap: "wrap",
                      }}
                    >
                      <span>{title}</span>
                      {sole && (
                        <Badge variant="warning">{t("identities.only")}</Badge>
                      )}
                    </span>
                    <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                      {password
                        ? t("identities.passwordHint")
                        : (identity.email ?? t("identities.noEmail"))}
                      {!password && identity.email_verified === false && (
                        <> · {t("identities.emailUnverified")}</>
                      )}
                    </span>
                  </div>
                  {password ? null : identity.can_unlink ? (
                    confirmId === identity.id ? (
                      <div
                        className="flex"
                        style={{ gap: 6, flexShrink: 0 }}
                        role="group"
                        aria-label={t("identities.confirmUnlink", {
                          name: title,
                        })}
                      >
                        <Button
                          type="button"
                          variant="danger"
                          size="xs"
                          data-testid={`identity-unlink-confirm-${identity.id}`}
                          onClick={() => {
                            setConfirmId(null);
                            onUnlink(identity.id);
                          }}
                        >
                          {t("identities.unlinkYes")}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            setConfirmId(null);
                          }}
                        >
                          {t("identities.unlinkNo")}
                        </Button>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        aria-disabled={busy}
                        aria-label={t("identities.unlinkAria", { name: title })}
                        data-testid={`identity-unlink-${identity.id}`}
                        onClick={() => {
                          if (!busy) setConfirmId(identity.id);
                        }}
                        style={{ gap: 6, flexShrink: 0 }}
                      >
                        {busy ? (
                          <Spinner size="sm" />
                        ) : (
                          <Unlink size={12} aria-hidden="true" />
                        )}
                        {t("identities.unlink")}
                      </Button>
                    )
                  ) : (
                    <span
                      style={{
                        fontSize: 11.5,
                        color: "var(--fg-2)",
                        maxWidth: 170,
                        textAlign: "right",
                      }}
                      data-testid={`identity-locked-${identity.id}`}
                    >
                      {t("identities.lockedHint")}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>

          {sole && (
            <p style={HINT} data-testid="identities-sole">
              {t("identities.soleNote")}
            </p>
          )}

          {failure && (
            <Notice
              tone={failure.code === "last_login_method" ? "warn" : "err"}
              role="alert"
              text={
                failure.code === "last_login_method"
                  ? t("identities.lastMethod")
                  : t(failureKey(failure.code))
              }
            />
          )}

          {free.length > 0 && (
            <div className="flex flex-col" style={{ gap: 8 }}>
              <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                {t("identities.addTitle")}
              </span>
              <div style={ACTIONS}>
                {free.map((provider) => {
                  const busy = linkingId === provider.id;
                  return (
                    <Button
                      key={provider.id}
                      type="button"
                      variant="outline"
                      aria-disabled={linkingId !== null}
                      data-testid={`identity-link-${provider.id}`}
                      style={{ gap: 8 }}
                      onClick={() => {
                        if (linkingId === null) onLink(provider.id);
                      }}
                    >
                      {busy ? (
                        <Spinner size="sm" />
                      ) : (
                        <Link2 size={14} aria-hidden="true" />
                      )}
                      {t("identities.link", { name: provider.label })}
                    </Button>
                  );
                })}
              </div>
              <p style={HINT}>{t("identities.linkHint")}</p>
            </div>
          )}
        </>
      )}
    </AccountCard>
  );
};
