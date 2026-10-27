import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  GIT_PROVIDERS,
  isGitProvider,
  useUpdateHostSettings,
  type GitHostSettings,
  type GitProvider,
  type UpdateGitHostSettingsRequest,
} from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Spinner } from "@shared/ui/Spinner";
import { pemProblem } from "../lib/pem";
import { CaCertificateInput } from "./CaCertificateInput";

export type HostSettingsDialogProps = {
  /** Настройки существующего сервера; null: добавляем новый. */
  settings: GitHostSettings | null;
  onClose: () => void;
};

type Choice = GitProvider | "auto";

// Хост из того, что вставили: «https://gitlab.hse.local:8443/team» тоже подходит.
const readHost = (
  value: string,
): { host: string; port: number | null } | null => {
  const text = value.trim().toLowerCase();
  if (text === "" || /\s/.test(text)) return null;
  const match =
    /^(?:[a-z][a-z0-9+.-]*:\/\/)?(?:[^@/]*@)?([a-z0-9.-]+)(?::(\d{1,5}))?(?:\/.*)?$/.exec(
      text,
    );
  const name = match?.[1];
  if (!name?.includes(".")) return null;
  const port = match?.[2] ? Number(match[2]) : null;
  if (port !== null && (port < 1 || port > 65535)) return null;
  return { host: name, port };
};

// Настройки одного сервера: тип сервера (если автоопределение ошиблось), свой
// сертификат центра выдачи и закреплённый сертификат. Проверку TLS отключить
// нельзя нигде.
export const HostSettingsDialog = ({
  settings,
  onClose,
}: HostSettingsDialogProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const uid = useId();
  const update = useUpdateHostSettings();
  const adding = settings === null;
  const initialChoice: Choice =
    settings?.provider_override && isGitProvider(settings.provider_override)
      ? settings.provider_override
      : "auto";

  const [hostText, setHostText] = useState("");
  const [choice, setChoice] = useState<Choice>(initialChoice);
  const [pem, setPem] = useState("");
  const [removeCa, setRemoveCa] = useState(false);
  const [removePin, setRemovePin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const typed = adding ? readHost(hostText) : null;
  const host = settings?.host ?? typed?.host ?? "";
  const port = settings ? (settings.port ?? null) : (typed?.port ?? null);
  const hostInvalid = adding && touched && typed === null;
  const pemEntered = pem.trim() !== "";
  const pemBad = pemEntered && pemProblem(pem) !== null;
  const busy = update.isPending;

  const changes: Omit<UpdateGitHostSettingsRequest, "host" | "port"> = {
    ...(choice !== initialChoice
      ? { provider_override: choice === "auto" ? null : choice }
      : {}),
    ...(pemEntered && !pemBad ? { ca_pem: pem.trim() } : {}),
    ...(removeCa && !pemEntered ? { ca_pem: null } : {}),
    ...(removePin ? { pinned_fingerprint: null } : {}),
  };
  const hasChanges = Object.keys(changes).length > 0;
  const canSave =
    !busy && host !== "" && !pemBad && (adding ? true : hasChanges);

  const close = (): void => {
    if (busy) return;
    onClose();
  };

  const save = async (): Promise<void> => {
    setError(null);
    try {
      await update.mutateAsync({ host, port, ...changes });
      toast.success(t("servers.saved", { host }));
      onClose();
    } catch (caught) {
      setError(describeGitError(caught, t("servers.saveFailed")));
    }
  };

  const forget = async (): Promise<void> => {
    setError(null);
    try {
      // Отдельного удаления нет: сброс всех трёх полей возвращает сервер к умолчанию.
      await update.mutateAsync({
        host,
        port,
        provider_override: null,
        ca_pem: null,
        pinned_fingerprint: null,
      });
      toast.success(t("servers.removed", { host }));
      onClose();
    } catch (caught) {
      setError(describeGitError(caught, t("servers.removeFailed")));
    }
  };

  const options: Choice[] = ["auto", ...GIT_PROVIDERS];

  return (
    <Modal
      isOpen
      onClose={close}
      width={560}
      title={
        adding
          ? t("servers.dialog.addTitle")
          : t("servers.dialog.editTitle", { host })
      }
      description={t("servers.dialog.description")}
      footer={
        <>
          {!adding && (
            <button
              type="button"
              className="btn danger"
              style={{ marginRight: "auto" }}
              disabled={busy}
              data-testid="host-settings-remove"
              onClick={() => {
                void forget();
              }}
            >
              {update.isPending && <Spinner size="sm" />}
              {t("servers.dialog.remove")}
            </button>
          )}
          <button type="button" className="btn" onClick={close} disabled={busy}>
            {t("servers.dialog.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={!canSave}
            data-testid="host-settings-save"
            onClick={() => {
              void save();
            }}
          >
            {update.isPending && <Spinner size="sm" />}
            {t("servers.dialog.save")}
          </button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 16 }}
        data-testid="host-settings"
      >
        {adding && (
          <div className="field">
            <label htmlFor={`${uid}-host`}>{t("servers.dialog.host")}</label>
            <input
              id={`${uid}-host`}
              type="text"
              className="input mono"
              value={hostText}
              autoFocus
              spellCheck={false}
              autoComplete="off"
              autoCapitalize="off"
              placeholder="gitlab.hse.local"
              aria-invalid={hostInvalid}
              onChange={(event) => {
                setHostText(event.target.value);
              }}
              onBlur={() => {
                setTouched(true);
              }}
            />
            {hostInvalid ? (
              <p
                className="text-xs"
                role="alert"
                style={{ margin: 0, color: "var(--c-err)" }}
              >
                {t("servers.dialog.hostInvalid")}
              </p>
            ) : (
              <p className="hint" style={{ margin: 0 }}>
                {t("servers.dialog.hostHint")}
              </p>
            )}
          </div>
        )}

        <fieldset
          className="flex flex-col"
          style={{ gap: 6, border: 0, margin: 0, padding: 0 }}
        >
          <legend style={{ fontSize: 12, fontWeight: 600, padding: 0 }}>
            {t("servers.dialog.provider")}
          </legend>
          <div role="radiogroup" className="flex flex-col" style={{ gap: 3 }}>
            {options.map((id) => (
              <label
                key={id}
                className="flex items-center"
                style={{
                  gap: 8,
                  padding: "5px 8px",
                  borderRadius: "var(--r-2)",
                  cursor: "pointer",
                  fontSize: 12.5,
                  background:
                    choice === id ? "var(--accent-soft)" : "transparent",
                }}
              >
                <input
                  type="radio"
                  name={`${uid}-provider`}
                  checked={choice === id}
                  onChange={() => {
                    setChoice(id);
                  }}
                  style={{ accentColor: "var(--accent)" }}
                />
                {id === "auto"
                  ? t("servers.dialog.auto")
                  : tRemote(`provider.${id}`)}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex flex-col" style={{ gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>
            {t("servers.dialog.ca")}
          </div>
          {settings?.ca_present && !removeCa ? (
            <div
              className="flex items-center"
              style={{ gap: 8, flexWrap: "wrap", fontSize: 12.5 }}
            >
              <span className="chip accent">{t("servers.caPresent")}</span>
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  setRemoveCa(true);
                }}
              >
                {t("servers.dialog.removeCa")}
              </button>
            </div>
          ) : (
            <>
              {removeCa && (
                <Notice
                  tone="info"
                  role="status"
                  text={t("servers.dialog.caWillGo")}
                />
              )}
              <CaCertificateInput
                value={pem}
                onChange={setPem}
                onReadError={() => {
                  setError(t("tls.ca.readFailed"));
                }}
                idPrefix="host-ca"
              />
            </>
          )}
        </div>

        {settings?.pinned_fingerprint && (
          <div className="flex flex-col" style={{ gap: 6 }}>
            <div style={{ fontSize: 12, fontWeight: 600 }}>
              {t("servers.dialog.pin")}
            </div>
            {removePin ? (
              <Notice
                tone="info"
                role="status"
                text={t("servers.dialog.pinWillGo")}
              />
            ) : (
              <>
                <CopyField
                  value={settings.pinned_fingerprint}
                  label={t("servers.dialog.pin")}
                />
                <button
                  type="button"
                  className="btn xs"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() => {
                    setRemovePin(true);
                  }}
                >
                  {t("servers.dialog.removePin")}
                </button>
              </>
            )}
          </div>
        )}

        <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
          {t("tls.noDisable")}
        </p>
        {error && <Notice tone="err" role="alert" text={error} />}
      </div>
    </Modal>
  );
};
