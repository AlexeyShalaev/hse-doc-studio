import { useId, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  gitRemoteApi,
  gitRemoteKeys,
  useSecretsStatus,
  type GitCredential,
  type PermissionProfile,
} from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import { Button } from "@shared/ui/Button";
import { Notice } from "@shared/ui/ConflictKit";
import { Input } from "@shared/ui/Input";
import { targetOfAddress } from "../lib/hostUrl";
import { defaultCredentialLabel, tokenCreateUrl } from "../lib/providerHelp";
import { useHostProvider } from "../model/useHostProvider";
import {
  verdictOfCheck,
  verdictOfError,
  type TokenVerdict,
} from "../model/tokenVerdict";
import { PatPanel, type PatDraft } from "./PatPanel";
import { TokenCheckCard } from "./TokenCheckCard";

export type AddTokenFormProps = {
  /**
   * Адрес репозитория, для которого нужен токен: сервер берётся из него. Не
   * задан: человек сам вводит сервер или адрес (раздел «Доступы git»).
   */
  url?: string | null;
  /** Начальное значение поля сервера, когда адрес не задан. */
  defaultServer?: string;
  /** Профиль прав каталога: под него ссылка на токен и проверка прав. */
  profile?: PermissionProfile | null;
  /** Раскрыть подробные шаги памятки о токене. */
  helpOpen?: boolean;
  /** Фокус в поле токена при показе. */
  autoFocus?: boolean;
  /** Токен проверен и сохранён как доступ git. */
  onSaved: (credential: GitCredential, verdict: TokenVerdict) => void;
};

const EMPTY_DRAFT: PatDraft = { token: "", username: "", label: "" };

// Токен не подходит: отказ сервера, истёк, мало прав. Такой доступ не сохраняем.
const rejected = (verdict: TokenVerdict): boolean =>
  verdict.kind === "too_narrow" ||
  verdict.kind === "expired" ||
  verdict.kind === "error";

type Check = null | "running" | TokenVerdict;

/**
 * Новый токен прямо там, где он нужен: памятка, поле, «Проверить и сохранить».
 * Тот же API, что у раздела «Доступы git» и окна подключения: токен
 * сохраняется доступом (зашифрованным, как везде), затем проверяется под профиль
 * прав. Не подошёл: доступ сразу удаляется, итог проверки виден под полем.
 * Поле токена очищается, как только запрос ушёл.
 */
export const AddTokenForm = ({
  url = null,
  defaultServer = "github.com",
  profile = null,
  helpOpen = true,
  autoFocus = true,
  onSaved,
}: AddTokenFormProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const uid = useId();
  const queryClient = useQueryClient();
  const secrets = useSecretsStatus();
  const secretsOk = secrets.data?.ok ?? true;
  const [server, setServer] = useState(defaultServer);
  const [draft, setDraft] = useState<PatDraft>(EMPTY_DRAFT);
  const [showToken, setShowToken] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<Check>(null);
  // Фокус в поле токена только при первом показе: пока человек правит адрес
  // сервера, поле токена может появиться заново и не должно забирать ввод.
  const [tokenFocus, setTokenFocus] = useState(autoFocus);

  const editable = url === null;
  const target = useMemo(
    () => targetOfAddress(editable ? server : url),
    [editable, server, url],
  );
  const host = useHostProvider(target);
  const parsed = host.url;
  const busy = check === "running";
  const providerName = tRemote(`provider.${parsed?.provider ?? "other"}`);
  const canSave =
    parsed !== null && secretsOk && !busy && draft.token.trim() !== "";

  const save = async (value?: string): Promise<void> => {
    if (!parsed?.host || !secretsOk || busy) return;
    const token = (value ?? draft.token).trim();
    if (token === "") return;
    setError(null);
    setCheck("running");
    let saved: GitCredential;
    try {
      // Прямо через API, без кэша: в списке доступов токен появится только
      // после проверки, иначе окно с выбором доступа увидит его раньше времени.
      saved = await gitRemoteApi.createCredential({
        kind: "pat",
        label:
          draft.label.trim() ||
          defaultCredentialLabel(providerName, parsed.host),
        host: parsed.host,
        ...(draft.username.trim() ? { username: draft.username.trim() } : {}),
        token,
      });
    } catch (caught) {
      setError(describeGitError(caught, t("pat.saveFailed")));
      setCheck(null);
      return;
    } finally {
      // Токен нужен только на время запроса: после него поле всегда пустое.
      setDraft((current) => ({ ...current, token: "" }));
      setShowToken(false);
    }
    let verdict: TokenVerdict;
    try {
      const result = profile
        ? await gitRemoteApi.checkCredential(saved.id, profile)
        : await gitRemoteApi.checkCredential(saved.id);
      verdict = verdictOfCheck(result);
    } catch (caught) {
      verdict = verdictOfError(caught, saved.expires_at);
    }
    if (rejected(verdict)) {
      void gitRemoteApi.deleteCredential(saved.id).catch(() => undefined);
      setCheck(verdict);
      return;
    }
    // Новый доступ виден в списке сразу, не дожидаясь перечитывания.
    queryClient.setQueryData<GitCredential[]>(
      gitRemoteKeys.credentials(),
      (list) =>
        list ? [...list.filter((c) => c.id !== saved.id), saved] : list,
    );
    void queryClient.invalidateQueries({
      queryKey: gitRemoteKeys.credentials(),
    });
    void queryClient.invalidateQueries({ queryKey: gitRemoteKeys.secrets() });
    setCheck(null);
    setDraft(EMPTY_DRAFT);
    onSaved(saved, verdict);
  };

  const feedback =
    check === null ? null : (
      <TokenCheckCard
        verdict={check === "running" ? null : check}
        provider={parsed?.provider ?? "other"}
        profile={profile}
        canRetry={false}
        createUrl={
          parsed
            ? tokenCreateUrl(parsed, { profile, subpath: host.subpath })
            : null
        }
      />
    );

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.75rem" }}
      data-testid="add-token-form"
    >
      {editable && (
        <Input
          id={`${uid}-server`}
          label={t("addToken.server")}
          hint={t("addToken.serverHint")}
          {...(server.trim() !== "" && target === null
            ? { error: t("addToken.serverInvalid") }
            : {})}
          value={server}
          onChange={(event) => {
            setServer(event.target.value);
            setTokenFocus(false);
            setCheck(null);
          }}
          isMono
          autoComplete="off"
          spellCheck={false}
          data-testid="add-token-server"
        />
      )}
      {!secretsOk && (
        <Notice tone="err" role="alert" text={t("secretsUnavailable")} />
      )}
      {parsed && (
        <PatPanel
          draft={draft}
          onChange={(next) => {
            setDraft(next);
            if (next.token !== draft.token && check !== "running") {
              setCheck(null);
            }
          }}
          showToken={showToken}
          onToggleShowToken={() => {
            setShowToken((current) => !current);
          }}
          url={parsed}
          disabled={busy || !secretsOk}
          error={error}
          helpOpen={helpOpen}
          serverVersion={host.detection.version}
          profile={profile}
          autoFocus={tokenFocus}
          feedback={feedback}
          onPasteToken={(token) => {
            void save(token);
          }}
        />
      )}
      {parsed && (
        <div>
          <Button
            size="sm"
            disabled={!canSave}
            onClick={() => {
              void save();
            }}
            data-testid="add-token-submit"
          >
            <ScanSearch size="0.75rem" aria-hidden="true" />
            {t("addToken.submit")}
          </Button>
        </div>
      )}
    </div>
  );
};
