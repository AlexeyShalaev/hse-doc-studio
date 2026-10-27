import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  gitRemoteApi,
  useCheckCredential,
  useCreateCredential,
  useUpdateCredential,
  type GitCredential,
} from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import {
  toHttpsUrl,
  toScpLikeUrl,
  type ParsedRemoteUrl,
} from "../lib/parseRemoteUrl";
import {
  deployKeyLabel,
  deployKeysOf,
  isDeployKey,
  repoPathOf,
  userKeysOf,
} from "../lib/keyScope";
import { defaultCredentialLabel } from "../lib/providerHelp";
import { NEW_CREDENTIAL } from "../ui/CredentialPicker";
import type { PatDraft } from "../ui/PatPanel";
import {
  verdictOfCheck,
  verdictOfError,
  type TokenCheckState,
} from "./tokenVerdict";

/**
 * Способ доступа: токен по https, ключ пользователя (ssh), deploy-ключ одного
 * репозитория (ssh) или `none`: открытый репозиторий без токена, только чтение.
 */
export type AccessMethod = "pat" | "ssh" | "deploy" | "none";

export type UseRemoteAuthOptions = {
  /** null: адрес ещё не введён или не разобран, выбирать пока нечего. */
  url: ParsedRemoteUrl | null;
  /** `fix_access`: адрес не меняется, доступ обновляется у уже подключённого проекта. */
  fixing: boolean;
  /** Доступ, с которым проект подключён сейчас (для `fix_access`). */
  bound: { id: string; label: string; kind: string } | null;
  credentials: GitCredential[];
  /** false: хранилище секретов недоступно, сохранить токен или ключ нельзя. */
  secretsOk: boolean;
  /** Добавляет способ «Публичный репозиторий» (без токена, только чтение). */
  allowAnonymous?: boolean;
  /** Доступ, выбранный заранее (например, в окне подключения). */
  initialCredentialId?: string | null;
  /** Доступ выбран или сохранён (null: без доступа): можно проверять подключение. */
  onResolved: (credentialId: string | null) => void;
};

const EMPTY_DRAFT: PatDraft = { token: "", username: "", label: "" };

const sameHost = (credential: GitCredential, host: string | null): boolean =>
  host !== null && credential.host.toLowerCase() === host.toLowerCase();

const methodOf = (url: ParsedRemoteUrl | null): AccessMethod =>
  url?.kind === "ssh" ? "ssh" : "pat";

// Состояние выбора доступа: токен по https, ключ по ssh или (для клонирования)
// открытый репозиторий. Общее для шага «Доступ» окна подключения и для мастера
// клонирования; поля рисует RemoteAuthFields, а кнопку действия каждый шаг свою.
export const useRemoteAuth = ({
  url,
  fixing,
  bound,
  credentials,
  secretsOk,
  allowAnonymous = false,
  initialCredentialId = null,
  onResolved,
}: UseRemoteAuthOptions) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const createCredential = useCreateCredential();
  const updateCredential = useUpdateCredential();

  // Способ, который выбрал человек; пока не выбирал, он следует за видом адреса.
  const [chosenMethod, setMethodState] = useState<AccessMethod | null>(null);
  // Привязанный ключ сам говорит, каким он был: ключ пользователя или deploy.
  const defaultMethod: AccessMethod =
    fixing && bound?.kind === "ssh_key" && url?.kind === "ssh"
      ? credentials.some((item) => item.id === bound.id && isDeployKey(item))
        ? "deploy"
        : "ssh"
      : methodOf(url);
  const method = chosenMethod ?? defaultMethod;
  const [draft, setDraft] = useState<PatDraft>(EMPTY_DRAFT);
  const [showToken, setShowToken] = useState(false);
  const [choice, setChoice] = useState<string | null>(initialCredentialId);
  const [sshChoice, setSshChoice] = useState<string | null>(
    initialCredentialId,
  );
  const [useOther, setUseOther] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Проверка токена: сохранённый доступ и что о нём сказал сервер.
  const [tokenCheck, setTokenCheck] = useState<TokenCheckState>({
    status: "idle",
  });
  // Токен заменён у привязанного доступа в этом окне: вставлять его снова не нужно.
  const [replacedId, setReplacedId] = useState<string | null>(null);
  const checkCredential = useCheckCredential();
  // Доступы, заведённые вставкой токена, но ещё не взятые в работу: если окно
  // закрыли, не оставляем их в списке.
  const [freshId, setFreshId] = useState<string | null>(null);
  const freshRef = useRef<string | null>(null);
  useEffect(
    () => () => {
      const id = freshRef.current;
      if (id) void gitRemoteApi.deleteCredential(id).catch(() => undefined);
    },
    [],
  );

  const host = url?.host ?? null;
  const providerName = tRemote(`provider.${url?.provider ?? "other"}`);

  const pats = useMemo(
    () =>
      credentials.filter(
        (credential) => credential.kind === "pat" && sameHost(credential, host),
      ),
    [credentials, host],
  );
  const allKeys = useMemo(
    () =>
      credentials.filter(
        (credential) =>
          credential.kind === "ssh_key" && sameHost(credential, host),
      ),
    [credentials, host],
  );
  const repoPath = url ? repoPathOf(url) : "";
  // Ключ пользователя и deploy-ключ репозитория лежат на сервере одинаково, но в
  // выборе не смешиваются: deploy-ключ чужого репозитория тут не подойдёт.
  const userKeys = useMemo(() => userKeysOf(allKeys), [allKeys]);
  const deployKeys = useMemo(
    () => deployKeysOf(allKeys, repoPath),
    [allKeys, repoPath],
  );
  const keys = method === "deploy" ? deployKeys : userKeys;

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
    (choice === NEW_CREDENTIAL ||
      choice === freshId ||
      pats.some((p) => p.id === choice))
      ? choice
      : defaultPat;
  const keyChoice =
    boundKey?.id ??
    (sshChoice !== null && keys.some((key) => key.id === sshChoice)
      ? sshChoice
      : (keys[0]?.id ?? null));
  const isKeyMethod = method === "ssh" || method === "deploy";

  const creatingPat = !boundPat && patChoice === NEW_CREDENTIAL;
  const tokenFilled = draft.token.trim() !== "";
  const boundReplaced = boundPat !== null && replacedId === boundPat.id;

  const clearSecret = (): void => {
    setDraft((current) => ({ ...current, token: "" }));
    setShowToken(false);
  };

  const savePat = async (): Promise<void> => {
    if (!url) return;
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
      onResolved(saved.id);
    } catch (caught) {
      setError(describeGitError(caught, t("pat.saveFailed")));
    } finally {
      // Токен нужен только на время запроса: после него поле всегда пустое.
      clearSecret();
      setIsSaving(false);
    }
  };

  // Проверка токена без репозитория: токен сохраняется как доступ (иначе сервер
  // его не увидит), затем спрашиваем, чей он, какие у него права и до какого
  // срока. Поле токена очищается сразу после сохранения. Токен не попадает ни в
  // состояние проверки, ни в ключи запросов.
  const checkToken = async (value?: string): Promise<void> => {
    if (!url || !secretsOk || isSaving) return;
    const token = (value ?? draft.token).trim();
    if (token === "") return;
    setError(null);
    setIsSaving(true);
    setTokenCheck({ status: "checking" });
    let savedId: string | null = null;
    try {
      let saved: GitCredential;
      if (boundPat) {
        saved = await updateCredential.mutateAsync({
          id: boundPat.id,
          params: { token },
        });
        setReplacedId(saved.id);
      } else {
        saved = await createCredential.mutateAsync({
          kind: "pat",
          label:
            draft.label.trim() ||
            defaultCredentialLabel(providerName, host ?? ""),
          host: host ?? "",
          ...(draft.username.trim() ? { username: draft.username.trim() } : {}),
          token,
        });
        // Предыдущая вставка не пригодилась: заменяем её новой.
        const old = freshRef.current;
        if (old) void gitRemoteApi.deleteCredential(old).catch(() => undefined);
        freshRef.current = saved.id;
        setFreshId(saved.id);
        setChoice(saved.id);
      }
      savedId = saved.id;
    } catch (caught) {
      setError(describeGitError(caught, t("pat.saveFailed")));
      setTokenCheck({ status: "idle" });
    } finally {
      // Токен нужен только на время запроса: после него поле всегда пустое.
      clearSecret();
    }
    if (savedId !== null) {
      await runCredentialCheck(savedId);
    }
    setIsSaving(false);
  };

  const runCredentialCheck = async (id: string): Promise<void> => {
    setTokenCheck({ status: "checking" });
    try {
      const result = await checkCredential.mutateAsync(id);
      setTokenCheck({
        status: "done",
        credentialId: id,
        verdict: verdictOfCheck(result),
        provider: result.provider_info,
      });
    } catch (caught) {
      setTokenCheck({
        status: "done",
        credentialId: id,
        verdict: verdictOfError(
          caught,
          credentials.find((item) => item.id === id)?.expires_at,
        ),
        provider: null,
      });
    }
  };

  const createKey = async (): Promise<void> => {
    if (!url) return;
    setError(null);
    setIsSaving(true);
    try {
      const created = await createCredential.mutateAsync({
        kind: "ssh_key",
        label:
          method === "deploy" && repoPath !== ""
            ? deployKeyLabel(repoPath)
            : t("ssh.defaultLabel", {
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
    if (method === "none") {
      onResolved(null);
      return;
    }
    if (isKeyMethod) {
      if (keyChoice) onResolved(keyChoice);
      return;
    }
    if (boundPat && boundReplaced && !tokenFilled) {
      onResolved(boundPat.id);
      return;
    }
    if (creatingPat || boundPat) {
      if (tokenFilled && secretsOk) void savePat();
      return;
    }
    // Доступ взят в работу: убирать его при закрытии окна уже нельзя.
    if (freshRef.current === patChoice) freshRef.current = null;
    onResolved(patChoice);
  };

  const canSubmit =
    !isSaving &&
    (method === "none"
      ? true
      : isKeyMethod
        ? keyChoice !== null
        : creatingPat || boundPat
          ? (tokenFilled && secretsOk) || (boundReplaced && !tokenFilled)
          : true);

  const submitLabel = isKeyMethod
    ? t("step.checkKey")
    : method === "pat" &&
        (creatingPat || boundPat) &&
        !(boundReplaced && !tokenFilled)
      ? t("step.saveAndCheck")
      : t("step.check");

  const mismatch: { text: string; target: string | null } | null =
    url && isKeyMethod && url.kind === "https"
      ? { text: t("mismatch.sshOnHttps"), target: toScpLikeUrl(url) }
      : url && method === "pat" && url.kind === "ssh"
        ? { text: t("mismatch.tokenOnSsh"), target: toHttpsUrl(url) }
        : null;

  return {
    allowAnonymous,
    host,
    method,
    setMethod: (next: AccessMethod): void => {
      setMethodState(next);
      setError(null);
    },
    draft,
    setDraft,
    showToken,
    toggleShowToken: (): void => {
      setShowToken((current) => !current);
    },
    error,
    isSaving,
    pats,
    keys,
    allKeys,
    boundPat,
    boundKey,
    patChoice,
    selectPat: (value: string): void => {
      setChoice(value);
      setError(null);
    },
    keyChoice,
    selectKey: setSshChoice,
    creatingPat,
    useOther,
    toggleUseOther: (): void => {
      setUseOther((current) => !current);
      setError(null);
    },
    createKey,
    tokenCheck,
    /** Доступ заведён вставкой токена и ещё не взят в работу. */
    freshId,
    checkToken,
    /** Проверить токен выбранного сохранённого доступа (или привязанного к проекту). */
    checkSaved: (): void => {
      const id = boundPat?.id ?? (creatingPat ? null : patChoice);
      if (id) void runCredentialCheck(id);
    },
    recheck: (): void => {
      if (tokenCheck.status === "done")
        void runCredentialCheck(tokenCheck.credentialId);
    },
    submit,
    canSubmit,
    submitLabel,
    mismatch,
  };
};

export type RemoteAuth = ReturnType<typeof useRemoteAuth>;
