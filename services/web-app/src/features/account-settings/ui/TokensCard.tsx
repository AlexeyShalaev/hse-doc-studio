import { useId, useState, type FormEvent } from "react";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Input, SecretOnce, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  ApiToken,
  CreateApiTokenRequest,
  TokenScope,
} from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS, HINT } from "../lib/styles";
import {
  DEFAULT_EXPIRY,
  TOKEN_EXPIRIES,
  TOKEN_SCOPES,
  formatDay,
  isExpired,
  scopeKey,
} from "../lib/tokens";
import { AccountCard } from "./parts";

export type TokensCardProps = {
  status: "loading" | "error" | "ready";
  tokens?: ApiToken[];
  /** Только что созданный токен: его значение показываем один раз. */
  created?: { token: string; name: string } | null;
  creating?: boolean;
  createFailure?: Failure | null;
  /** Идентификатор токена, который отзывают сейчас. */
  revokingId?: string | null;
  failure?: Failure | null;
  /** Форма создания открыта с самого начала (для галереи). */
  startOpen?: boolean;
  onRetry?: () => void;
  /** done вызывают после успеха: форма очищается и закрывается. */
  onCreate: (body: CreateApiTokenRequest, done: () => void) => void;
  onRevoke: (id: string) => void;
  onDismissCreated?: () => void;
};

const NAME_MAX = 80;

/** Личные токены доступа: для CLI и скриптов. Значение видно только при создании. */
export const TokensCard = ({
  status,
  tokens = [],
  created = null,
  creating = false,
  createFailure = null,
  revokingId = null,
  failure = null,
  startOpen = false,
  onRetry,
  onCreate,
  onRevoke,
  onDismissCreated,
}: TokensCardProps) => {
  const { t, i18n } = useTranslation("account");
  const uid = useId();
  const [open, setOpen] = useState(startOpen);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<TokenScope[]>(["api"]);
  const [expiry, setExpiry] = useState<number | null>(DEFAULT_EXPIRY);
  const [touched, setTouched] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const trimmed = name.replace(/\s+/g, " ").trim();
  const nameError = touched && trimmed === "" ? t("tokens.nameRequired") : null;
  const scopeError = touched && scopes.length === 0;

  const toggle = (scope: TokenScope, on: boolean) => {
    setScopes((current) =>
      on ? [...current, scope] : current.filter((s) => s !== scope),
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (creating || trimmed === "" || scopes.length === 0) return;
    onCreate(
      {
        name: trimmed,
        scopes: TOKEN_SCOPES.filter((s) => scopes.includes(s)),
        expires_in_days: expiry,
      },
      () => {
        setName("");
        setScopes(["api"]);
        setExpiry(DEFAULT_EXPIRY);
        setTouched(false);
        setOpen(false);
      },
    );
  };

  const expiryOptions = TOKEN_EXPIRIES.map((days) => ({
    value: days === null ? "never" : String(days),
    label:
      days === null
        ? t("tokens.expiry.never")
        : t("tokens.expiry.days", { count: days }),
  }));

  return (
    <AccountCard
      id="account-tokens"
      title={t("tokens.title")}
      sub={t("tokens.sub")}
      testId="account-tokens"
    >
      {created && (
        <div data-testid="token-created">
          <SecretOnce
            label={t("tokens.created.label", { name: created.name })}
            value={created.token}
            hint={t("tokens.created.hint")}
            onClose={() => onDismissCreated?.()}
          />
        </div>
      )}

      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="tokens-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("tokens.loading")}</span>
        </div>
      )}

      {status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("tokens.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("tokens.retry")}
              </button>
            )
          }
        />
      )}

      {status === "ready" && (
        <>
          {tokens.length === 0 ? (
            <p style={HINT} data-testid="tokens-empty">
              {t("tokens.empty")}
            </p>
          ) : (
            <ul
              style={{ listStyle: "none", margin: 0, padding: 0 }}
              className="flex flex-col"
              data-testid="tokens-list"
            >
              {tokens.map((token) => {
                const expired = isExpired(token);
                const busy = revokingId === token.id;
                return (
                  <li
                    key={token.id}
                    data-testid={`token-${token.id}`}
                    data-expired={expired ? "true" : undefined}
                    className="flex"
                    style={{
                      gap: 12,
                      padding: "10px 0",
                      borderBottom: "1px dashed var(--border)",
                      alignItems: "flex-start",
                    }}
                  >
                    <KeyRound
                      size={18}
                      aria-hidden="true"
                      style={{
                        color: "var(--fg-2)",
                        flexShrink: 0,
                        marginTop: 2,
                      }}
                    />
                    <div
                      className="flex flex-col"
                      style={{ gap: 4, flex: 1, minWidth: 0 }}
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
                        <span style={{ overflowWrap: "anywhere" }}>
                          {token.name}
                        </span>
                        {expired && (
                          <Badge variant="error">{t("tokens.expired")}</Badge>
                        )}
                      </span>
                      <code
                        style={{ fontSize: 11.5, color: "var(--fg-2)" }}
                        data-testid={`token-prefix-${token.id}`}
                      >
                        {token.prefix}…
                      </code>
                      <span
                        className="flex"
                        style={{ gap: 6, flexWrap: "wrap" }}
                      >
                        {token.scopes.map((scope) => (
                          <Badge key={scope} variant="subtle">
                            {t(`tokens.scopes.${scopeKey(scope)}.title`)}
                          </Badge>
                        ))}
                      </span>
                      <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                        {token.expires_at === null
                          ? t("tokens.noExpiry")
                          : expired
                            ? t("tokens.expiredOn", {
                                date: formatDay(
                                  token.expires_at,
                                  i18n.language,
                                ),
                              })
                            : t("tokens.expiresOn", {
                                date: formatDay(
                                  token.expires_at,
                                  i18n.language,
                                ),
                              })}
                        {" · "}
                        {token.last_used_at === null
                          ? t("tokens.neverUsed")
                          : t("tokens.lastUsed", {
                              date: formatDay(
                                token.last_used_at,
                                i18n.language,
                              ),
                            })}
                      </span>
                    </div>
                    {confirmId === token.id ? (
                      <div
                        className="flex"
                        style={{ gap: 6, flexShrink: 0 }}
                        role="group"
                        aria-label={t("tokens.confirmRevoke", {
                          name: token.name,
                        })}
                      >
                        <Button
                          type="button"
                          variant="danger"
                          size="xs"
                          data-testid={`token-revoke-confirm-${token.id}`}
                          onClick={() => {
                            setConfirmId(null);
                            onRevoke(token.id);
                          }}
                        >
                          {t("tokens.revokeYes")}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            setConfirmId(null);
                          }}
                        >
                          {t("tokens.revokeNo")}
                        </Button>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        aria-disabled={busy}
                        aria-label={t("tokens.revokeAria", {
                          name: token.name,
                        })}
                        data-testid={`token-revoke-${token.id}`}
                        onClick={() => {
                          if (!busy) setConfirmId(token.id);
                        }}
                        style={{ gap: 6, flexShrink: 0 }}
                      >
                        {busy ? (
                          <Spinner size="sm" />
                        ) : (
                          <Trash2 size={12} aria-hidden="true" />
                        )}
                        {t("tokens.revoke")}
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {failure && (
            <Notice
              tone="err"
              role="alert"
              text={t(failureKey(failure.code))}
            />
          )}

          {open ? (
            <form
              onSubmit={submit}
              className="flex flex-col"
              style={{
                gap: 12,
                maxWidth: 420,
                padding: 14,
                borderRadius: "var(--r-2)",
                background: "var(--bg-2)",
              }}
              data-testid="token-form"
            >
              <Input
                id={`${uid}-name`}
                label={t("tokens.name")}
                name="token-name"
                autoComplete="off"
                maxLength={NAME_MAX}
                value={name}
                placeholder={t("tokens.namePlaceholder")}
                onChange={(e) => {
                  setName(e.target.value);
                }}
                readOnly={creating}
                hint={t("tokens.nameHint")}
                {...(nameError ? { error: nameError } : {})}
              />

              <fieldset
                className="flex flex-col"
                style={{ gap: 8, border: 0, margin: 0, padding: 0 }}
              >
                <legend
                  style={{ fontSize: 12.5, fontWeight: 500, marginBottom: 6 }}
                >
                  {t("tokens.scopesLegend")}
                </legend>
                {TOKEN_SCOPES.map((scope) => (
                  <label
                    key={scope}
                    className="flex"
                    style={{
                      gap: 10,
                      alignItems: "flex-start",
                      fontSize: 12.5,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope)}
                      onChange={(e) => {
                        toggle(scope, e.target.checked);
                      }}
                      style={{ marginTop: 3 }}
                      data-testid={`token-scope-${scopeKey(scope)}`}
                    />
                    <span className="flex flex-col" style={{ gap: 2 }}>
                      <span>{t(`tokens.scopes.${scopeKey(scope)}.title`)}</span>
                      <span style={HINT}>
                        {t(`tokens.scopes.${scopeKey(scope)}.hint`)}
                      </span>
                    </span>
                  </label>
                ))}
                {scopeError && (
                  <span
                    role="alert"
                    style={{ fontSize: 12, color: "var(--c-err)" }}
                  >
                    {t("tokens.scopesRequired")}
                  </span>
                )}
              </fieldset>

              <div className="flex flex-col" style={{ gap: 6 }}>
                <label
                  htmlFor={`${uid}-expiry`}
                  style={{ fontSize: 12.5, fontWeight: 500 }}
                >
                  {t("tokens.expiryLabel")}
                </label>
                <Select
                  id={`${uid}-expiry`}
                  value={expiry === null ? "never" : String(expiry)}
                  options={expiryOptions}
                  isDisabled={creating}
                  onValueChange={(value) => {
                    setExpiry(value === "never" ? null : Number(value));
                  }}
                />
                {expiry === null && (
                  <span style={HINT}>{t("tokens.expiry.neverHint")}</span>
                )}
              </div>

              {createFailure && (
                <Notice
                  tone={createFailure.code === "rate_limited" ? "warn" : "err"}
                  role="alert"
                  text={t(failureKey(createFailure.code))}
                />
              )}

              <div style={ACTIONS}>
                <Button
                  type="submit"
                  aria-disabled={creating}
                  style={{ gap: 8 }}
                  data-testid="token-submit"
                >
                  {creating ? (
                    <Spinner size="sm" />
                  ) : (
                    <KeyRound size={14} aria-hidden="true" />
                  )}
                  {creating ? t("tokens.creating") : t("tokens.create")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setOpen(false);
                    setTouched(false);
                  }}
                >
                  {t("tokens.cancel")}
                </Button>
              </div>
            </form>
          ) : (
            <div style={ACTIONS}>
              <Button
                type="button"
                variant="outline"
                data-testid="token-new"
                style={{ gap: 8 }}
                onClick={() => {
                  setOpen(true);
                }}
              >
                <Plus size={14} aria-hidden="true" />
                {t("tokens.new")}
              </Button>
            </div>
          )}
        </>
      )}
    </AccountCard>
  );
};
