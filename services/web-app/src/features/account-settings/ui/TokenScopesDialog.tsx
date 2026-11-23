import { useState } from "react";
import { Check, Minus, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { ApiToken, TokenScope } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { HINT } from "../lib/styles";
import {
  TOKEN_SCOPES,
  offeredScopes,
  scopeDiff,
  scopeKey,
  touchesMcp,
} from "../lib/tokens";

export type TokenScopesDialogProps = {
  /** Токен, права которого правим; null закрывает окно. */
  token: ApiToken | null;
  instanceAdmin?: boolean;
  saving?: boolean;
  failure?: Failure | null;
  /** done вызывают после успеха: окно показывает итог. */
  onSave: (scopes: TokenScope[], done: () => void) => void;
  onClose: () => void;
};

type Step = "edit" | "confirm" | "done";

const LIST = { listStyle: "none", margin: 0, padding: 0 } as const;

/**
 * «Изменить права» токена: те же галочки, что при создании, с отмеченными нынешними правами, затем сводка
 * «добавится / уберётся» и сохранение. Сам токен не меняется, поэтому CLI и ИИ-клиенты перенастраивать не нужно.
 */
export const TokenScopesDialog = ({
  token,
  instanceAdmin = false,
  saving = false,
  failure = null,
  onSave,
  onClose,
}: TokenScopesDialogProps) => {
  const { t } = useTranslation("account");
  return (
    <Modal
      isOpen={token !== null}
      onClose={onClose}
      title={token ? t("tokens.edit.title", { name: token.name }) : undefined}
      width={520}
    >
      {token && (
        // Ключ сбрасывает выбор при открытии другого токена.
        <Body
          key={token.id}
          token={token}
          instanceAdmin={instanceAdmin}
          saving={saving}
          failure={failure}
          onSave={onSave}
          onClose={onClose}
        />
      )}
    </Modal>
  );
};

const Body = ({
  token,
  instanceAdmin,
  saving,
  failure,
  onSave,
  onClose,
}: Required<Omit<TokenScopesDialogProps, "token">> & { token: ApiToken }) => {
  const { t } = useTranslation("account");
  const [scopes, setScopes] = useState<TokenScope[]>(token.scopes);
  const [step, setStep] = useState<Step>("edit");
  const offered = offeredScopes(instanceAdmin, token);
  const chosen = TOKEN_SCOPES.filter((s) => scopes.includes(s));
  const diff = scopeDiff(token.scopes, chosen);
  const changed = diff.added.length + diff.removed.length > 0;
  const empty = chosen.length === 0;
  const mcp = touchesMcp(diff);
  const title = (scope: TokenScope) =>
    t(`tokens.scopes.${scopeKey(scope)}.title`);

  const toggle = (scope: TokenScope, on: boolean) => {
    setScopes((current) =>
      on ? [...current, scope] : current.filter((s) => s !== scope),
    );
  };

  if (step === "done") {
    return (
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem", padding: "1rem 1.5rem 1.5rem" }}
        data-testid="token-scopes-done"
      >
        <Notice tone="info" role="status" text={t("tokens.edit.done")} />
        <p style={{ ...HINT, margin: 0 }}>{t("tokens.edit.effect")}</p>
        {mcp && (
          <div data-testid="token-scopes-reconnect">
            <Notice tone="warn" text={t("tokens.edit.mcpReconnect")} />
          </div>
        )}
        <div className="flex" style={{ justifyContent: "flex-end" }}>
          <Button
            type="button"
            onClick={onClose}
            data-testid="token-scopes-close"
          >
            {t("tokens.edit.close")}
          </Button>
        </div>
      </div>
    );
  }

  if (step === "confirm") {
    return (
      <div
        className="flex flex-col"
        style={{ gap: "0.875rem", padding: "1rem 1.5rem 1.5rem" }}
        data-testid="token-scopes-confirm"
      >
        <p style={{ margin: 0, fontSize: "0.8125rem" }}>
          {t("tokens.edit.confirmLead")}
        </p>
        {diff.added.length > 0 && (
          <section className="flex flex-col" style={{ gap: "0.375rem" }}>
            <h3 style={{ margin: 0, fontSize: "0.78125rem", fontWeight: 600 }}>
              {t("tokens.edit.added")}
            </h3>
            <ul style={LIST} data-testid="token-scopes-added">
              {diff.added.map((scope) => (
                <li
                  key={scope}
                  className="flex"
                  style={{ gap: "0.5rem", fontSize: "0.78125rem" }}
                >
                  <Plus
                    size="0.875rem"
                    aria-hidden="true"
                    style={{
                      color: "var(--c-ok)",
                      flexShrink: 0,
                      marginTop: "0.125rem",
                    }}
                  />
                  <span className="flex flex-col" style={{ gap: "0.125rem" }}>
                    <span>{title(scope)}</span>
                    <span style={HINT}>
                      {t(`tokens.scopes.${scopeKey(scope)}.hint`)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {diff.removed.length > 0 && (
          <section className="flex flex-col" style={{ gap: "0.375rem" }}>
            <h3 style={{ margin: 0, fontSize: "0.78125rem", fontWeight: 600 }}>
              {t("tokens.edit.removed")}
            </h3>
            <ul style={LIST} data-testid="token-scopes-removed">
              {diff.removed.map((scope) => (
                <li
                  key={scope}
                  className="flex"
                  style={{ gap: "0.5rem", fontSize: "0.78125rem" }}
                >
                  <Minus
                    size="0.875rem"
                    aria-hidden="true"
                    style={{
                      color: "var(--c-err)",
                      flexShrink: 0,
                      marginTop: "0.125rem",
                    }}
                  />
                  <span>{title(scope)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        <p style={{ ...HINT, margin: 0 }}>{t("tokens.edit.effect")}</p>
        {mcp && (
          <p style={{ ...HINT, margin: 0 }}>{t("tokens.edit.mcpReconnect")}</p>
        )}
        {failure && (
          <Notice
            tone={failure.code === "rate_limited" ? "warn" : "err"}
            role="alert"
            text={t(
              failure.code === "not_found"
                ? "tokens.edit.notFound"
                : failureKey(failure.code),
            )}
          />
        )}
        <div
          className="flex"
          style={{
            gap: "0.5rem",
            justifyContent: "flex-end",
            flexWrap: "wrap",
          }}
        >
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setStep("edit");
            }}
            disabled={saving}
          >
            {t("tokens.edit.back")}
          </Button>
          <Button
            type="button"
            aria-disabled={saving}
            data-testid="token-scopes-save"
            style={{ gap: "0.5rem" }}
            onClick={() => {
              if (saving) return;
              onSave(chosen, () => {
                setStep("done");
              });
            }}
          >
            {saving ? (
              <Spinner size="sm" />
            ) : (
              <Check size="0.875rem" aria-hidden="true" />
            )}
            {saving ? t("tokens.edit.saving") : t("tokens.edit.save")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="flex flex-col"
      style={{ gap: "0.75rem", padding: "1rem 1.5rem 1.5rem" }}
      data-testid="token-scopes-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (changed && !empty) setStep("confirm");
      }}
    >
      <p style={{ ...HINT, margin: 0 }}>
        {t(
          token.origin === "device"
            ? "tokens.edit.bodyDevice"
            : "tokens.edit.body",
        )}
      </p>
      <fieldset
        className="flex flex-col"
        style={{ gap: "0.625rem", border: 0, margin: 0, padding: 0 }}
      >
        <legend
          style={{
            fontSize: "0.78125rem",
            fontWeight: 500,
            marginBottom: "0.375rem",
          }}
        >
          {t("tokens.scopesLegend")}
        </legend>
        {offered.map((scope) => (
          <label
            key={scope}
            className="flex"
            style={{
              gap: "0.625rem",
              alignItems: "flex-start",
              fontSize: "0.78125rem",
            }}
          >
            <input
              type="checkbox"
              checked={scopes.includes(scope)}
              onChange={(e) => {
                toggle(scope, e.target.checked);
              }}
              style={{ marginTop: "0.1875rem" }}
              data-testid={`token-edit-scope-${scopeKey(scope)}`}
            />
            <span className="flex flex-col" style={{ gap: "0.125rem" }}>
              <span>{title(scope)}</span>
              <span style={HINT}>
                {t(`tokens.scopes.${scopeKey(scope)}.hint`)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
      {empty && (
        <span
          role="alert"
          style={{ fontSize: "0.75rem", color: "var(--c-err)" }}
        >
          {t("tokens.scopesRequired")}
        </span>
      )}
      <div
        className="flex"
        style={{ gap: "0.5rem", justifyContent: "flex-end", flexWrap: "wrap" }}
      >
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("tokens.cancel")}
        </Button>
        <Button
          type="submit"
          disabled={!changed || empty}
          data-testid="token-scopes-next"
        >
          {t("tokens.edit.next")}
        </Button>
      </div>
    </form>
  );
};
