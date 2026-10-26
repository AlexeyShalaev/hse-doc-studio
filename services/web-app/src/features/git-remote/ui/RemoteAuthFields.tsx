import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import type { AccessMethod, RemoteAuth } from "../model/useRemoteAuth";
import { BrowserLoginCard } from "./BrowserLoginCard";
import { CredentialPicker } from "./CredentialPicker";
import { PatPanel } from "./PatPanel";
import { SshKeyPanel } from "./SshKeyPanel";

export type RemoteAuthFieldsProps = {
  auth: RemoteAuth;
  url: ParsedRemoteUrl;
  fixing?: boolean;
  /** Доступ, с которым проект подключён сейчас (для `fix_access`). */
  bound?: { id: string; label: string; kind: string } | null;
  isLoadingCredentials: boolean;
  secretsOk: boolean;
  onSwitchUrl: (value: string) => void;
  /** Показать карточку «Вход через браузер: скоро». */
  showBrowserLogin?: boolean;
};

// Поля доступа к репозиторию: способ (токен, ключ), сохранённые доступы и формы
// создания нового. Общие для шага «Доступ» окна подключения и для мастера
// клонирования; кнопки действия у каждого шага свои.
export const RemoteAuthFields = ({
  auth,
  url,
  fixing = false,
  bound = null,
  isLoadingCredentials,
  secretsOk,
  onSwitchUrl,
  showBrowserLogin = true,
}: RemoteAuthFieldsProps) => {
  const { t } = useTranslation("gitAccess");
  const {
    method,
    mismatch,
    pats,
    boundPat,
    boundKey,
    creatingPat,
    error,
    isSaving,
  } = auth;
  const host = auth.host ?? "";

  const methods: AccessMethod[] = auth.allowAnonymous
    ? ["pat", "ssh", "none"]
    : ["pat", "ssh"];

  return (
    <>
      {!secretsOk && (
        <Notice tone="err" role="alert" text={t("secretsUnavailable")} />
      )}

      {!fixing && (
        <div
          className="seg"
          role="group"
          aria-label={t("method.label")}
          style={{ alignSelf: "flex-start", flexWrap: "wrap" }}
        >
          {methods.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={method === value}
              className={method === value ? "active" : undefined}
              onClick={() => {
                auth.setMethod(value);
              }}
            >
              {t(`method.${value}`)}
            </button>
          ))}
        </div>
      )}

      {mismatch && (
        <Notice
          tone="info"
          role="status"
          text={mismatch.text}
          action={
            !fixing && mismatch.target ? (
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  const target = mismatch.target;
                  if (!target) return;
                  onSwitchUrl(target);
                }}
              >
                {t("mismatch.replace", { target: mismatch.target })}
              </button>
            ) : undefined
          }
        />
      )}

      {isLoadingCredentials && method !== "none" && (
        <div className="flex items-center dim" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          {t("picker.loading")}
        </div>
      )}

      {method === "none" && (
        <Notice tone="info" role="status" text={t("none.hint")} />
      )}

      {method === "pat" && !isLoadingCredentials && (
        <>
          {!boundPat && pats.length > 0 && (
            <CredentialPicker
              credentials={pats}
              value={auth.patChoice}
              host={host}
              onChange={auth.selectPat}
            />
          )}
          {(creatingPat || boundPat) && (
            <PatPanel
              draft={auth.draft}
              onChange={auth.setDraft}
              showToken={auth.showToken}
              onToggleShowToken={auth.toggleShowToken}
              url={url}
              existing={boundPat}
              helpOpen={pats.length === 0 && !boundPat}
              disabled={!secretsOk || isSaving}
              error={error}
            />
          )}
          {!creatingPat && !boundPat && error && (
            <Notice tone="err" role="alert" text={error} />
          )}
        </>
      )}

      {method === "ssh" && !isLoadingCredentials && (
        <SshKeyPanel
          url={url}
          keys={boundKey ? [boundKey] : auth.keys}
          selectedId={auth.keyChoice}
          onSelect={auth.selectKey}
          onCreate={() => {
            void auth.createKey();
          }}
          isCreating={isSaving}
          disabled={!secretsOk}
          error={error}
        />
      )}

      {fixing && bound && (
        <button
          type="button"
          className="sync-history-link"
          onClick={auth.toggleUseOther}
        >
          {auth.useOther ? t("fix.useBound") : t("fix.useOther")}
        </button>
      )}

      {showBrowserLogin && <BrowserLoginCard />}
    </>
  );
};
