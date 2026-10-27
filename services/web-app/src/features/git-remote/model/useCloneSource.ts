import { useCallback, useMemo, useRef, useState } from "react";
import { useProbe, type Probe } from "@entities/git-remote";
import { parseRemoteUrl } from "../lib/parseRemoteUrl";
import {
  cloneVerdictFromError,
  cloneVerdictFromProbe,
  type CloneVerdict,
} from "./cloneVerdict";

export type CloneTab = "url" | "bundle";

export type CloneCheck =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "done"; verdict: CloneVerdict; probe: Probe | null };

export type CloneSourceInit = { url: string; credentialId: string | null };

// Откуда клонируем: адрес репозитория (с проверкой доступа) или файл bundle.
// Состояние держит мастер, а не шаг: при «Назад» из следующих шагов введённое
// и результат проверки остаются на месте.
export const useCloneSource = (initial: CloneSourceInit | null) => {
  const probe = useProbe();
  const [tab, setTab] = useState<CloneTab>("url");
  const [urlText, setUrlText] = useState(initial?.url ?? "");
  const [tokenStripped, setTokenStripped] = useState(false);
  const [credentialId, setCredentialId] = useState<string | null>(
    initial?.credentialId ?? null,
  );
  const [branch, setBranch] = useState("");
  const [check, setCheck] = useState<CloneCheck>({ status: "idle" });
  const [bundleFile, setBundleFile] = useState<File | null>(null);
  const [bundlePassword, setBundlePassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const runId = useRef(0);

  const parsed = useMemo(
    () => parseRemoteUrl(urlText, { allow_local: true }),
    [urlText],
  );
  const repoUrl = parsed.ok ? parsed.url : null;

  // Другой адрес или ветка: прежний результат проверки уже ни о чём.
  const invalidate = useCallback((): void => {
    runId.current += 1;
    setCheck({ status: "idle" });
  }, []);

  // Токен из адреса убираем и из самого поля: «мы его убрали» должно быть правдой.
  const changeUrl = (value: string): void => {
    const next = parseRemoteUrl(value, { allow_local: true });
    // Вставка или автозаполнение приходят одним куском, а не по символу.
    const pasted = value.length - urlText.length > 1;
    invalidate();
    setError(null);
    setBranch("");
    if (pasted && next.ok && next.url.token_stripped) {
      setUrlText(next.url.display_url);
      setTokenStripped(true);
      return;
    }
    setUrlText(value);
    setTokenStripped(false);
  };

  const commitUrl = (): void => {
    if (parsed.ok && parsed.url.token_stripped) {
      setUrlText(parsed.url.display_url);
      setTokenStripped(true);
    }
  };

  const runCheck = useCallback(
    async (
      overrides: { credentialId?: string | null; branch?: string } = {},
    ) => {
      if (!repoUrl) return;
      const id =
        overrides.credentialId !== undefined
          ? overrides.credentialId
          : credentialId;
      const branchValue = (overrides.branch ?? branch).trim();
      runId.current += 1;
      const run = runId.current;
      setCredentialId(id);
      setError(null);
      setCheck({ status: "checking" });
      let verdict: CloneVerdict;
      let answer: Probe | null = null;
      try {
        answer = await probe.mutateAsync({
          url: repoUrl.display_url,
          credential_id: id,
          ...(branchValue !== "" ? { branch: branchValue } : {}),
        });
        verdict = cloneVerdictFromProbe(answer);
      } catch (caught) {
        verdict = cloneVerdictFromError(caught);
      }
      // Пока шла проверка, человек мог поменять адрес или повторить её.
      if (run !== runId.current) return;
      setCheck({ status: "done", verdict, probe: answer });
    },
    [branch, credentialId, probe, repoUrl],
  );

  return {
    tab,
    setTab: (next: CloneTab): void => {
      setTab(next);
      setError(null);
    },
    urlText,
    setUrlText: (value: string): void => {
      invalidate();
      setError(null);
      setBranch("");
      setTokenStripped(false);
      setUrlText(value);
    },
    changeUrl,
    commitUrl,
    tokenStripped,
    parsed,
    repoUrl,
    credentialId,
    branch,
    setBranch,
    check,
    runCheck,
    resetCheck: invalidate,
    bundleFile,
    setBundleFile: (file: File | null): void => {
      setBundleFile(file);
      setBundlePassword("");
      setError(null);
    },
    bundlePassword,
    setBundlePassword: (value: string): void => {
      setBundlePassword(value);
      setError(null);
    },
    /** Ошибка, с которой человека вернули на шаг: отказ при запуске. */
    error,
    setError,
  };
};

export type CloneSource = ReturnType<typeof useCloneSource>;
