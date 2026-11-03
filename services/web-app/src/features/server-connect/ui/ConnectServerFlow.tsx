import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  GitServerLoginFlow,
  useGitServerCheck,
  type GitServerCheck,
} from "@entities/git-server";
import { gitClonePath } from "@entities/git-sync";
import { studioCloneUrl, type ConnectTarget } from "@entities/local-studio";
import { useProjects } from "@entities/project";

export type ConnectServerFlowProps = {
  /** Адрес сервера и проект из ссылки облака; без адреса экран спросит его сам. */
  target: ConnectTarget;
  /** Имя этой Студии в «Токенах» сервера. */
  clientName: string;
  /** Перейти по адресу приложения (проект, мастер клонирования, главная). */
  onNavigate: (path: string) => void;
};

type Stage =
  | { kind: "address" }
  | { kind: "check"; server: string }
  | { kind: "login"; server: string }
  | { kind: "done"; check: GitServerCheck; credentialId: string };

const hostOf = (url: string): string => {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
};

/**
 * Экран «Подключиться к серверу» локальной Студии (docs/design/local-from-cloud.md):
 * адрес → проверка версии и прежнего входа → вход кодом устройства → проект
 * (открыть, если уже есть, иначе мастер клонирования с готовым адресом и доступом).
 */
export const ConnectServerFlow = ({
  target,
  clientName,
  onNavigate,
}: ConnectServerFlowProps) => {
  const [stage, setStage] = useState<Stage>(
    target.server
      ? { kind: "check", server: target.server }
      : { kind: "address" },
  );
  const server =
    stage.kind === "check" || stage.kind === "login" ? stage.server : null;
  const check = useGitServerCheck(server);

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16, width: "100%", maxWidth: 560, padding: "32px 24px" }}
      data-testid="connect-server"
      data-stage={stage.kind}
    >
      <Header />
      {stage.kind === "address" && (
        <AddressForm
          onSubmit={(url) => {
            setStage({ kind: "check", server: url });
          }}
        />
      )}
      {(stage.kind === "check" || stage.kind === "login") && (
        <CheckStage
          server={stage.server}
          query={check}
          login={stage.kind === "login"}
          clientName={clientName}
          onEdit={() => {
            setStage({ kind: "address" });
          }}
          onLogin={() => {
            setStage({ kind: "login", server: stage.server });
          }}
          onCancelLogin={() => {
            setStage({ kind: "check", server: stage.server });
          }}
          onConnected={(found, credentialId) => {
            setStage({ kind: "done", check: found, credentialId });
          }}
        />
      )}
      {stage.kind === "done" && (
        <Done
          check={stage.check}
          credentialId={stage.credentialId}
          projectId={target.projectId}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
};

const Header = () => {
  const { t } = useTranslation("localStudio");
  return (
    <header className="flex flex-col" style={{ gap: 6 }}>
      <h1
        className="flex items-center"
        style={{ margin: 0, fontSize: 20, fontWeight: 600, gap: 10 }}
      >
        <Server size={20} aria-hidden="true" />
        {t("connectLocal.title")}
      </h1>
      <p className="dim" style={{ margin: 0, fontSize: 13 }}>
        {t("connectLocal.lead")}
      </p>
    </header>
  );
};

const AddressForm = ({ onSubmit }: { onSubmit: (url: string) => void }) => {
  const { t } = useTranslation("localStudio");
  const [url, setUrl] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (url.trim() !== "") onSubmit(url.trim());
  };
  return (
    <form
      className="flex flex-col"
      style={{ gap: 12 }}
      onSubmit={submit}
      noValidate
      data-testid="connect-server-address"
    >
      <Input
        label={t("connectLocal.url")}
        value={url}
        placeholder="https://studio.example.org"
        hint={t("connectLocal.urlHint")}
        autoFocus
        autoComplete="url"
        spellCheck={false}
        onChange={(event) => {
          setUrl(event.target.value);
        }}
        data-testid="connect-server-url"
      />
      <Button
        type="submit"
        disabled={url.trim() === ""}
        style={{ alignSelf: "flex-end" }}
        data-testid="connect-server-check"
      >
        {t("connectLocal.next")}
      </Button>
    </form>
  );
};

const COMPAT_TONE = {
  local_older: "warn",
  local_newer: "warn",
  unknown: "info",
} as const;

const CompatNotice = ({ check }: { check: GitServerCheck }) => {
  const { t } = useTranslation("localStudio");
  if (check.compat === "same" || check.compat === "compatible") return null;
  return (
    <div data-testid="connect-server-compat" data-compat={check.compat}>
      <Notice
        tone={COMPAT_TONE[check.compat]}
        role="status"
        text={t(`connectLocal.compat.${check.compat}`, {
          local: check.local_version,
          server: check.server_version,
        })}
      />
    </div>
  );
};

const CheckStage = ({
  server,
  query,
  login,
  clientName,
  onEdit,
  onLogin,
  onCancelLogin,
  onConnected,
}: {
  server: string;
  query: ReturnType<typeof useGitServerCheck>;
  login: boolean;
  clientName: string;
  onEdit: () => void;
  onLogin: () => void;
  onCancelLogin: () => void;
  onConnected: (check: GitServerCheck, credentialId: string) => void;
}) => {
  const { t } = useTranslation("localStudio");
  if (query.isLoading) {
    return (
      <span
        className="flex items-center dim"
        style={{ gap: 8 }}
        data-testid="connect-server-checking"
      >
        <Spinner size="sm" />
        {t("connectLocal.checking", { host: hostOf(server) })}
      </span>
    );
  }
  if (query.isError || !query.data) {
    const code = failureCode(query.error);
    return (
      <div className="flex flex-col" style={{ gap: 10 }}>
        <Notice
          tone="err"
          role="alert"
          text={
            code
              ? `${t("connectLocal.checkFailed", { url: server })} ${t(`errors:code.${code}`)}`
              : t("connectLocal.checkFailed", { url: server })
          }
        />
        <Button
          type="button"
          variant="ghost"
          onClick={onEdit}
          style={{ alignSelf: "flex-start" }}
          data-testid="connect-server-edit"
        >
          {t("connectLocal.edit")}
        </Button>
      </div>
    );
  }
  const found = query.data;
  const connected = found.state === "ok" && found.credential_id !== null;
  return (
    <div className="flex flex-col" style={{ gap: 12 }}>
      <div
        className="card flex flex-col"
        style={{ padding: "12px 14px", gap: 4 }}
        data-testid="connect-server-card"
      >
        <span style={{ fontWeight: 600, fontSize: 14 }}>
          {hostOf(found.server_url)}
        </span>
        <span className="dim" style={{ fontSize: 12.5 }}>
          {t("connectLocal.versions", {
            server: found.server_version,
            local: found.local_version,
          })}
        </span>
        {connected && found.account_name && (
          <span style={{ fontSize: 12.5, color: "var(--c-ok)" }}>
            {t("connectLocal.signedIn", { name: found.account_name })}
          </span>
        )}
      </div>
      <CompatNotice check={found} />
      {login ? (
        <GitServerLoginFlow
          initialUrl={found.server_url}
          autoStart
          clientName={clientName}
          onApproved={(credentialId) => {
            onConnected(found, credentialId);
          }}
          onCancel={onCancelLogin}
        />
      ) : (
        <div className="flex" style={{ gap: 8, justifyContent: "flex-end" }}>
          <Button type="button" variant="ghost" onClick={onEdit}>
            {t("connectLocal.edit")}
          </Button>
          {connected && found.credential_id ? (
            <Button
              type="button"
              onClick={() => {
                if (found.credential_id)
                  onConnected(found, found.credential_id);
              }}
              data-testid="connect-server-continue"
            >
              {t("connectLocal.continue")}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={onLogin}
              data-testid="connect-server-login"
            >
              {t("connectLocal.connect", { host: hostOf(found.server_url) })}
            </Button>
          )}
        </div>
      )}
      {!login && !connected && (
        <span className="dim" style={{ fontSize: 12 }}>
          {t("connectLocal.connectHint")}
        </span>
      )}
    </div>
  );
};

const Done = ({
  check,
  credentialId,
  projectId,
  onNavigate,
}: {
  check: GitServerCheck;
  credentialId: string;
  projectId: string | null;
  onNavigate: (path: string) => void;
}) => {
  const { t } = useTranslation("localStudio");
  const projects = useProjects();
  const known = projectId
    ? projects.data?.some((project) => project.id === projectId)
    : undefined;

  useEffect(() => {
    if (!projectId || known === undefined) return;
    onNavigate(
      known
        ? `/projects/${projectId}/documents`
        : gitClonePath({
            url: studioCloneUrl(check.server_url, projectId),
            credentialId,
          }),
    );
  }, [projectId, known, check.server_url, credentialId, onNavigate]);

  if (projectId) {
    return (
      <span
        className="flex items-center dim"
        style={{ gap: 8 }}
        data-testid="connect-server-opening"
      >
        <Spinner size="sm" />
        {t("connectLocal.opening")}
      </span>
    );
  }
  return (
    <div
      className="flex flex-col"
      style={{ gap: 12 }}
      data-testid="connect-server-done"
    >
      <span
        className="flex items-center"
        style={{ gap: 8, fontSize: 13.5, color: "var(--c-ok)" }}
        role="status"
      >
        <CheckCircle2 size={16} aria-hidden="true" />
        {t("connectLocal.done", { host: hostOf(check.server_url) })}
      </span>
      <span className="dim" style={{ fontSize: 12.5 }}>
        {t("connectLocal.doneHint")}
      </span>
      <div className="flex" style={{ gap: 8, justifyContent: "flex-end" }}>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            onNavigate("/");
          }}
        >
          {t("connectLocal.home")}
        </Button>
        <Button
          type="button"
          onClick={() => {
            onNavigate(gitClonePath());
          }}
          data-testid="connect-server-clone"
        >
          {t("connectLocal.clone")}
        </Button>
      </div>
    </div>
  );
};
