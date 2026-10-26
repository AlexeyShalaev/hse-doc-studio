import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateCredential,
  useUpdateCredential,
  type GitCredential,
} from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import {
  toHttpsUrl,
  toScpLikeUrl,
  type ParsedRemoteUrl,
} from "../lib/parseRemoteUrl";
import { defaultCredentialLabel } from "../lib/providerHelp";
import { BrowserLoginCard } from "./BrowserLoginCard";
import { CredentialPicker, NEW_CREDENTIAL } from "./CredentialPicker";
import { PatPanel, type PatDraft } from "./PatPanel";
import { ProviderChip } from "./ProviderChip";
import { SshKeyPanel } from "./SshKeyPanel";
import { StepLayout } from "./StepLayout";

export type AccessMethod = "pat" | "ssh";

export type AccessStepProps = {
  url: ParsedRemoteUrl;
  /** `fix_access`: адрес не меняется, доступ обновляется у уже подключённого проекта. */
  fixing: boolean;
  /** Доступ, с которым проект подключён сейчас (для `fix_access`). */
  bound: { id: string; label: string; kind: string } | null;
  credentials: GitCredential[];
  isLoadingCredentials: boolean;
  /** false: хранилище секретов недоступно, сохранить токен или ключ нельзя. */
  secretsOk: boolean;
  /** Доступ выбран (или сохранён): можно проверять подключение. */
  onContinue: (credentialId: string) => void;
  onBack: () => void;
  onSwitchUrl: (value: string) => void;
};

const EMPTY_DRAFT: PatDraft = { token: "", username: "", label: "" };

const sameHost = (credential: GitCredential, host: string | null): boolean =>
  host !== null && credential.host.toLowerCase() === host.toLowerCase();

const methodOf = (url: ParsedRemoteUrl): AccessMethod =>
  url.kind === "ssh" ? "ssh" : "pat";

// Шаг 2. Как репозиторий узнает, что это ты: токен по https или ключ по ssh.
export const AccessStep = ({
  url,
  fixing,
  bound,
  credentials,
  isLoadingCredentials,
  secretsOk,
  onContinue,
  onBack,
  onSwitchUrl,
}: AccessStepProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const createCredential = useCreateCredential();
  const updateCredential = useUpdateCredential();

  const [method, setMethod] = useState<AccessMethod>(methodOf(url));
  const [draft, setDraft] = useState<PatDraft>(EMPTY_DRAFT);
  const [showToken, setShowToken] = useState(false);
  const [choice, setChoice] = useState<string | null>(null);
  const [sshChoice, setSshChoice] = useState<string | null>(null);
  const [useOther, setUseOther] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const host = url.host;
  const providerName = tRemote(`provider.${url.provider}`);

  const pats = useMemo(
    () =>
      credentials.filter(
        (credential) => credential.kind === "pat" && sameHost(credential, host),
      ),
    [credentials, host],
  );
  const keys = useMemo(
    () =>
      credentials.filter(
        (credential) =>
          credential.kind === "ssh_key" && sameHost(credential, host),
      ),
    [credentials, host],
  );

  // Обновляем токен у доступа, с которым проект уже связан, пока человек не
  // решил выбрать другой.
  const boundPat =
    fixing && !useOther && bound?.kind === "pat"
      ? (credentials.find((credential) => credential.id === bound.id) ?? null)
      : null;
  const boundKey =
    fixing && !useOther && bound?.kind === "ssh_key"
      ? (credentials.find((credential) => credential.id === bound.id) ?? null)
      : null;

  // Выбор по умолчанию считаем при показе, а не в эффекте: так он не мигает.
  const defaultPat =
    pats.find((credential) => credential.status !== "auth_failed")?.id ??
    NEW_CREDENTIAL;
  const patChoice =
    choice !== null &&
    (choice === NEW_CREDENTIAL || pats.some((p) => p.id === choice))
      ? choice
      : defaultPat;
  const keyChoice =
    boundKey?.id ??
    (sshChoice !== null && keys.some((key) => key.id === sshChoice)
      ? sshChoice
      : (keys[0]?.id ?? null));

  const creatingPat = !boundPat && patChoice === NEW_CREDENTIAL;
  const tokenFilled = draft.token.trim() !== "";

  const clearSecret = (): void => {
    setDraft((current) => ({ ...current, token: "" }));
    setShowToken(false);
  };

  const savePat = async (): Promise<void> => {
    setError(null);
    setIsSaving(true);
    try {
      const token = draft.token.trim();
      const saved = boundPat
        ? await updateCredential.mutateAsync({
            id: boundPat.id,
            params: { token },
          })
        : await createCredential.mutateAsync({
            kind: "pat",
            label:
              draft.label.trim() ||
              defaultCredentialLabel(providerName, host ?? ""),
            host: host ?? "",
            ...(draft.username.trim()
              ? { username: draft.username.trim() }
              : {}),
            token,
          });
      onContinue(saved.id);
    } catch (caught) {
      setError(describeGitError(caught, t("pat.saveFailed")));
    } finally {
      // Токен нужен только на время запроса: после него поле всегда пустое.
      clearSecret();
      setIsSaving(false);
    }
  };

  const createKey = async (): Promise<void> => {
    setError(null);
    setIsSaving(true);
    try {
      const created = await createCredential.mutateAsync({
        kind: "ssh_key",
        label: t("ssh.defaultLabel", {
          name: defaultCredentialLabel(providerName, host ?? ""),
        }),
        host: host ?? "",
        ...(url.port !== null ? { port: url.port } : {}),
      });
      setSshChoice(created.id);
    } catch (caught) {
      setError(describeGitError(caught, t("ssh.createFailed")));
    } finally {
      setIsSaving(false);
    }
  };

  const submit = (): void => {
    if (isSaving) return;
    if (method === "ssh") {
      if (keyChoice) onContinue(keyChoice);
      return;
    }
    if (creatingPat || boundPat) {
      if (tokenFilled && secretsOk) void savePat();
      return;
    }
    onContinue(patChoice);
  };

  const canSubmit =
    !isSaving &&
    (method === "ssh"
      ? keyChoice !== null
      : creatingPat || boundPat
        ? tokenFilled && secretsOk
        : true);

  const submitLabel =
    method === "ssh"
      ? t("step.checkKey")
      : creatingPat || boundPat
        ? t("step.saveAndCheck")
        : t("step.check");

  const mismatch: { text: string; target: string | null } | null =
    method === "ssh" && url.kind === "https"
      ? { text: t("mismatch.sshOnHttps"), target: toScpLikeUrl(url) }
      : method === "pat" && url.kind === "ssh"
        ? { text: t("mismatch.tokenOnSsh"), target: toHttpsUrl(url) }
        : null;

  return (
    <StepLayout
      id="connect-access"
      aria-label={tRemote("connect.steps.access")}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) submit();
      }}
      start={
        <button type="button" className="btn" onClick={onBack}>
          {fixing ? tRemote("connect.cancel") : tRemote("connect.back")}
        </button>
      }
      end={
        <button type="submit" className="btn primary" disabled={!canSubmit}>
          {isSaving && <Spinner size="sm" />}
          {submitLabel}
        </button>
      }
    >
      {fixing && (
        <div
          style={{
            padding: "8px 10px",
            borderRadius: "var(--r-2)",
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
          }}
        >
          <ProviderChip url={url} />
        </div>
      )}

      {!secretsOk && (
        <Notice tone="err" role="alert" text={t("secretsUnavailable")} />
      )}

      {!fixing && (
        <div
          className="seg"
          role="group"
          aria-label={t("method.label")}
          style={{ alignSelf: "flex-start" }}
        >
          {(["pat", "ssh"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={method === value}
              className={method === value ? "active" : undefined}
              onClick={() => {
                setMethod(value);
                setError(null);
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

      {isLoadingCredentials && (
        <div className="flex items-center dim" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          {t("picker.loading")}
        </div>
      )}

      {method === "pat" && !isLoadingCredentials && (
        <>
          {!boundPat && pats.length > 0 && (
            <CredentialPicker
              credentials={pats}
              value={patChoice}
              host={host ?? ""}
              onChange={(value) => {
                setChoice(value);
                setError(null);
              }}
            />
          )}
          {(creatingPat || boundPat) && (
            <PatPanel
              draft={draft}
              onChange={setDraft}
              showToken={showToken}
              onToggleShowToken={() => {
                setShowToken((current) => !current);
              }}
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
          keys={boundKey ? [boundKey] : keys}
          selectedId={keyChoice}
          onSelect={setSshChoice}
          onCreate={() => {
            void createKey();
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
          onClick={() => {
            setUseOther((current) => !current);
            setError(null);
          }}
        >
          {useOther ? t("fix.useBound") : t("fix.useOther")}
        </button>
      )}

      <BrowserLoginCard />
    </StepLayout>
  );
};
