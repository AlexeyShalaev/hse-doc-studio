import { useEffect, useRef, useState, type FormEvent } from "react";
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  DeviceCodeDisplay,
  deviceCountdown,
  useNowTick,
} from "@shared/ui/DeviceCodeCard";
import {
  useCancelGitServerLogin,
  useGitServerLogin,
  useStartGitServerLogin,
} from "../api/gitServerQueries";
import type { GitServerLogin } from "../model/gitServer.schema";

export type GitServerLoginFlowProps = {
  /** Адрес, с которого начать (повторный вход на известный сервер). */
  initialUrl?: string;
  /** Начать вход сразу с `initialUrl`, без формы адреса (человек уже нажал «Подключиться»). */
  autoStart?: boolean;
  /** Имя этого устройства в «Токенах» сервера. */
  clientName: string;
  onApproved: (credentialId: string) => void;
  onCancel: () => void;
};

/**
 * Вход локальной Студии на сервер Студии кодом устройства (раздел 10.13):
 * адрес → код и ссылка на подтверждение → итог. Опрос сервера ведёт локальный
 * api, экран только спрашивает его состояние.
 */
export const GitServerLoginFlow = ({
  initialUrl = "",
  autoStart = false,
  clientName,
  onApproved,
  onCancel,
}: GitServerLoginFlowProps) => {
  const { t } = useTranslation("gitServer");
  const [url, setUrl] = useState(initialUrl);
  const [loginId, setLoginId] = useState<string | null>(null);
  const start = useStartGitServerLogin();
  const cancel = useCancelGitServerLogin();
  const login = useGitServerLogin(loginId);
  const [notified, setNotified] = useState<string | null>(null);

  const current = login.data ?? start.data ?? null;
  if (
    current?.state === "approved" &&
    current.credential_id &&
    notified !== current.login_id
  ) {
    setNotified(current.login_id);
    onApproved(current.credential_id);
  }

  const begin = () => {
    if (url.trim() === "" || start.isPending) return;
    start.mutate(
      { server_url: url.trim(), client_name: clientName },
      {
        onSuccess: (started) => {
          setLoginId(started.login_id);
        },
      },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    begin();
  };

  const autoStarted = useRef(false);
  useEffect(() => {
    if (!autoStart || autoStarted.current || initialUrl.trim() === "") return;
    autoStarted.current = true;
    begin();
    // Только при монтировании: повторный вход начинает человек.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const restart = () => {
    if (loginId) cancel.mutate(loginId);
    setLoginId(null);
    start.reset();
  };

  if (loginId === null || current === null) {
    const code = start.isError ? failureCode(start.error) : null;
    return (
      <form
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        onSubmit={submit}
        noValidate
        data-testid="git-server-login"
      >
        <Input
          label={t("login.url")}
          value={url}
          placeholder={t("login.urlPlaceholder")}
          hint={t("login.urlHint")}
          autoFocus
          autoComplete="url"
          spellCheck={false}
          onChange={(event) => {
            setUrl(event.target.value);
          }}
          {...(code ? { error: t(`errors:code.${code}`) } : {})}
          data-testid="git-server-url"
        />
        <div
          className="flex"
          style={{ gap: "0.5rem", justifyContent: "flex-end" }}
        >
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t("login.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={url.trim() === "" || start.isPending}
            data-testid="git-server-login-submit"
          >
            {start.isPending && <Spinner size="sm" />}
            {t("login.submit")}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <LoginState
      login={current}
      onCancel={() => {
        restart();
        onCancel();
      }}
      onRestart={restart}
    />
  );
};

const LoginState = ({
  login,
  onCancel,
  onRestart,
}: {
  login: GitServerLogin;
  onCancel: () => void;
  onRestart: () => void;
}) => {
  const { t } = useTranslation("gitServer");
  const now = useNowTick();
  if (login.state === "pending") {
    const left = login.expires_at
      ? deviceCountdown(login.expires_at, now)
      : null;
    return (
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="git-server-login-code"
        data-state="pending"
      >
        <DeviceCodeDisplay
          code={login.user_code ?? ""}
          title={t("login.codeTitle")}
          hint={t("login.codeHint")}
          testId="git-server-login-user-code"
        />
        <span
          className="flex items-center dim"
          style={{ gap: "0.5rem", fontSize: "0.8125rem" }}
          role="status"
          aria-live="polite"
        >
          <Spinner size="sm" />
          {t("login.waiting")}
          {left && ` · ${t("login.expiresIn", { time: left })}`}
        </span>
        <div
          className="flex"
          style={{ gap: "0.5rem", justifyContent: "flex-end" }}
        >
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t("login.cancel")}
          </Button>
          {login.verification_uri_complete && (
            <a
              href={login.verification_uri_complete}
              target="_blank"
              rel="noreferrer noopener"
              className="btn primary"
              style={{ textDecoration: "none" }}
              data-testid="git-server-login-open-browser"
            >
              <ExternalLink size="0.75rem" aria-hidden="true" />
              {t("login.openBrowser")}
            </a>
          )}
        </div>
      </div>
    );
  }
  const tone = login.state === "approved" ? "info" : "warn";
  const text =
    login.state === "error" && login.code
      ? `${t("login.result.error")} ${t(`errors:code.${login.code}`)}`
      : t(`login.result.${login.state}`);
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.75rem" }}
      data-testid="git-server-login-code"
      data-state={login.state}
    >
      <Notice tone={tone} role="status" text={text} />
      {login.state !== "approved" && (
        <div
          className="flex"
          style={{ gap: "0.5rem", justifyContent: "flex-end" }}
        >
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t("login.cancel")}
          </Button>
          <Button type="button" onClick={onRestart}>
            {t("login.again")}
          </Button>
        </div>
      )}
    </div>
  );
};
