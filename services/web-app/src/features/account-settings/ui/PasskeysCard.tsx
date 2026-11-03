import { useState } from "react";
import { FingerprintPattern, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Badge, Button, Input, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AccountPasskey, AccountPasskeyList } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS, HINT } from "../lib/styles";
import type { PasskeyBusy } from "../model/usePasskeys";
import { AccountCard } from "./parts";

export type PasskeysCardProps = {
  status: "loading" | "error" | "ready";
  data?: AccountPasskeyList | undefined;
  /** Браузер умеет WebAuthn и страница открыта в защищённом контексте. */
  browserSupported: boolean;
  busy?: PasskeyBusy;
  failure?: Failure | null;
  onRetry?: () => void;
  onAdd: () => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
};

const formatDay = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

/** Passkey аккаунта: вход без пароля с этого и других устройств. */
export const PasskeysCard = ({
  status,
  data,
  browserSupported,
  busy = null,
  failure = null,
  onRetry,
  onAdd,
  onRename,
  onDelete,
}: PasskeysCardProps) => {
  const { t } = useTranslation("account");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const items = data?.items ?? [];
  const atLimit = data !== undefined && items.length >= data.limit;
  const enabled = data?.enabled === true;
  const canAdd = enabled && browserSupported && !atLimit;
  const adding = busy?.kind === "add";

  const blockedHint = !enabled
    ? t("passkeys.disabledHint")
    : !browserSupported
      ? t("passkeys.unsupportedHint")
      : atLimit
        ? t("passkeys.limitHint", { count: data.limit })
        : null;

  const row = (passkey: AccountPasskey) => {
    const renaming = busy?.kind === "rename" && busy.id === passkey.id;
    const deleting = busy?.kind === "delete" && busy.id === passkey.id;
    return (
      <li
        key={passkey.id}
        data-testid={`passkey-item-${passkey.id}`}
        className="flex flex-col"
        style={{
          gap: 8,
          padding: "10px 0",
          borderBottom: "1px dashed var(--border)",
        }}
      >
        <div className="flex items-center" style={{ gap: 12 }}>
          <FingerprintPattern
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
              <span
                style={{ overflowWrap: "anywhere" }}
                data-testid={`passkey-name-${passkey.id}`}
              >
                {passkey.name}
              </span>
              {passkey.synced && (
                <Badge variant="info">{t("passkeys.synced")}</Badge>
              )}
              {!passkey.domain_matches && (
                <Badge variant="warning">
                  {t("passkeys.otherDomain", { domain: passkey.domain })}
                </Badge>
              )}
            </span>
            <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
              {t("passkeys.created", { when: formatDay(passkey.created_at) })}
              {" · "}
              {passkey.last_used_at
                ? t("passkeys.lastUsed", {
                    when: formatPastTime(passkey.last_used_at),
                  })
                : t("passkeys.neverUsed")}
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            data-testid={`passkey-rename-${passkey.id}`}
            aria-label={t("passkeys.renameAria", { name: passkey.name })}
            onClick={() => {
              setEditing(passkey.id);
              setDraft(passkey.name);
              setConfirmId(null);
            }}
          >
            <Pencil size={12} aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="xs"
            data-testid={`passkey-delete-${passkey.id}`}
            aria-disabled={deleting}
            aria-label={t("passkeys.deleteAria", { name: passkey.name })}
            onClick={() => {
              setConfirmId(passkey.id);
              setEditing(null);
            }}
            style={{ gap: 6 }}
          >
            {deleting ? (
              <Spinner size="sm" />
            ) : (
              <Trash2 size={12} aria-hidden="true" />
            )}
            {t("passkeys.delete")}
          </Button>
        </div>

        {editing === passkey.id && (
          <form
            style={ACTIONS}
            onSubmit={(event) => {
              event.preventDefault();
              const name = draft.trim();
              if (!name || renaming) return;
              onRename(passkey.id, name);
              setEditing(null);
            }}
          >
            <div style={{ flex: 1, minWidth: 180 }}>
              <Input
                aria-label={t("passkeys.nameLabel")}
                value={draft}
                maxLength={64}
                autoFocus
                data-testid="passkey-rename-input"
                onChange={(e) => {
                  setDraft(e.target.value);
                }}
              />
            </div>
            <Button
              type="submit"
              size="sm"
              data-testid="passkey-rename-save"
              disabled={draft.trim() === ""}
            >
              {t("passkeys.save")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(null);
              }}
            >
              {t("passkeys.cancel")}
            </Button>
          </form>
        )}

        {confirmId === passkey.id && (
          <div
            style={ACTIONS}
            role="group"
            aria-label={t("passkeys.confirmDelete", { name: passkey.name })}
          >
            <span style={{ fontSize: 12.5, flex: 1, minWidth: 200 }}>
              {t("passkeys.confirmDelete", { name: passkey.name })}
            </span>
            <Button
              type="button"
              variant="danger"
              size="sm"
              data-testid="passkey-delete-confirm"
              onClick={() => {
                onDelete(passkey.id);
                setConfirmId(null);
              }}
            >
              {t("passkeys.delete")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setConfirmId(null);
              }}
            >
              {t("passkeys.cancel")}
            </Button>
          </div>
        )}
      </li>
    );
  };

  return (
    <AccountCard
      id="account-passkeys"
      title={t("passkeys.title")}
      sub={t("passkeys.sub")}
      testId="account-passkeys"
    >
      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="passkeys-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("passkeys.loading")}</span>
        </div>
      )}

      {status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("passkeys.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("passkeys.retry")}
              </button>
            )
          }
        />
      )}

      {status === "ready" && (
        <>
          {items.length === 0 ? (
            <p
              style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}
              data-testid="passkeys-empty"
            >
              {t("passkeys.empty")}
            </p>
          ) : (
            <ul
              style={{ listStyle: "none", margin: 0, padding: 0 }}
              className="flex flex-col"
              data-testid="passkeys-list"
            >
              {items.map(row)}
            </ul>
          )}

          {failure && (
            <div data-testid="passkeys-failure">
              <Notice
                tone="err"
                role="alert"
                text={t(failureKey(failure.code))}
              />
            </div>
          )}

          <div style={ACTIONS}>
            <Button
              type="button"
              data-testid="passkey-add"
              disabled={!canAdd}
              aria-disabled={adding}
              onClick={() => {
                if (!adding) onAdd();
              }}
              style={{ gap: 8 }}
            >
              {adding ? (
                <Spinner size="sm" />
              ) : (
                <Plus size={14} aria-hidden="true" />
              )}
              {t("passkeys.add")}
            </Button>
          </div>
          {blockedHint ? (
            <p style={HINT} data-testid="passkeys-blocked">
              {blockedHint}
            </p>
          ) : (
            <p style={HINT}>
              {data?.domain
                ? t("passkeys.domainHint", { domain: data.domain })
                : t("passkeys.hint")}
            </p>
          )}
        </>
      )}
    </AccountCard>
  );
};
