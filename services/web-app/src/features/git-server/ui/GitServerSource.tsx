import { useState } from "react";
import { ChevronLeft, Plus, Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { i18n } from "@shared/lib";
import { Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { EmptyState } from "@shared/ui/EmptyState";
import { SearchInput } from "@shared/ui/SearchInput";
import {
  GitServerLoginFlow,
  useGitServerProjects,
  useGitServers,
  type GitProject,
  type GitServerItem,
} from "@entities/git-server";

export type GitServerSourceProps = {
  /** Имя этой Студии в «Токенах» сервера. */
  clientName: string;
  /** Проект выбран: адрес клонирования и доступ к серверу. */
  onPick: (project: GitProject, credentialId: string) => void;
  /** Галерея: сразу проекты этого сервера или форма входа. */
  initialView?: View;
};

export type View =
  | { kind: "servers" }
  | { kind: "login"; url?: string }
  | { kind: "projects"; credentialId: string };

const dateOf = (iso: string | null): string | null =>
  iso
    ? new Date(iso).toLocaleDateString(
        i18n.language === "en" ? "en-GB" : "ru-RU",
      )
    : null;

/**
 * Источник «Сервер HSE Doc Studio» в мастере клонирования (раздел 10.13):
 * подключённые серверы или вход на новый, затем список проектов сервера.
 * Выбранный проект клонируется обычным потоком стадии 1.
 */
export const GitServerSource = ({
  clientName,
  onPick,
  initialView = { kind: "servers" },
}: GitServerSourceProps) => {
  const servers = useGitServers();
  const [view, setView] = useState<View>(initialView);

  if (view.kind === "login") {
    return (
      <GitServerLoginFlow
        {...(view.url ? { initialUrl: view.url } : {})}
        clientName={clientName}
        onApproved={(credentialId) => {
          setView({ kind: "projects", credentialId });
        }}
        onCancel={() => {
          setView({ kind: "servers" });
        }}
      />
    );
  }
  if (view.kind === "projects") {
    return (
      <ServerProjects
        credentialId={view.credentialId}
        onBack={() => {
          setView({ kind: "servers" });
        }}
        onRelogin={() => {
          const server = servers.data?.items.find(
            (item) => item.credential_id === view.credentialId,
          );
          setView({
            kind: "login",
            ...(server ? { url: server.server_url } : {}),
          });
        }}
        onPick={(project) => {
          onPick(project, view.credentialId);
        }}
      />
    );
  }
  return (
    <ServerList
      items={servers.data?.items ?? []}
      loading={servers.isLoading}
      failed={servers.isError}
      onOpen={(item) => {
        if (item.state === "ok") {
          setView({ kind: "projects", credentialId: item.credential_id });
        } else {
          setView({ kind: "login", url: item.server_url });
        }
      }}
      onLogin={() => {
        setView({ kind: "login" });
      }}
    />
  );
};

const STATE_COLOR: Record<GitServerItem["state"], string> = {
  ok: "var(--c-ok)",
  expired: "var(--c-warn)",
  revoked: "var(--c-err)",
  unreachable: "var(--fg-2)",
};

const ServerList = ({
  items,
  loading,
  failed,
  onOpen,
  onLogin,
}: {
  items: GitServerItem[];
  loading: boolean;
  failed: boolean;
  onOpen: (item: GitServerItem) => void;
  onLogin: () => void;
}) => {
  const { t } = useTranslation("gitServer");
  return (
    <div
      className="flex flex-col"
      style={{ gap: 10 }}
      data-testid="git-server-picker"
    >
      <span style={{ fontSize: 12.5, fontWeight: 600 }}>
        {t("servers.title")}
      </span>
      {loading && <Spinner size="sm" />}
      {failed && (
        <Notice tone="err" role="alert" text={t("servers.loadFailed")} />
      )}
      {!loading && !failed && items.length === 0 && (
        <p className="dim" style={{ margin: 0, fontSize: 13 }}>
          {t("servers.empty")}
        </p>
      )}
      {items.map((item) => {
        const until = dateOf(item.expires_at);
        return (
          <button
            key={item.credential_id}
            type="button"
            className="flex items-center"
            style={{
              gap: 12,
              padding: "10px 12px",
              borderRadius: "var(--r-2)",
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
              textAlign: "left",
              cursor: "pointer",
            }}
            onClick={() => {
              onOpen(item);
            }}
            data-testid={`git-server-${item.credential_id}`}
            data-state={item.state}
          >
            <Server size={18} aria-hidden="true" style={{ flexShrink: 0 }} />
            <span className="flex flex-col" style={{ gap: 2, flex: 1 }}>
              <span style={{ fontWeight: 500, fontSize: 13 }}>{item.host}</span>
              <span className="dim" style={{ fontSize: 12 }}>
                {[
                  item.account_name
                    ? t("servers.account", { name: item.account_name })
                    : null,
                  until ? t("servers.accessUntil", { date: until }) : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
            <span style={{ fontSize: 12, color: STATE_COLOR[item.state] }}>
              {item.state === "ok"
                ? t("servers.open")
                : `${t(`servers.state.${item.state}`)} · ${t("servers.relogin")}`}
            </span>
          </button>
        );
      })}
      <Button
        type="button"
        variant="ghost"
        onClick={onLogin}
        style={{ alignSelf: "flex-start" }}
        data-testid="git-server-login-open"
      >
        <Plus size={12} aria-hidden="true" />
        {t("servers.loginOpen")}
      </Button>
    </div>
  );
};

const ServerProjects = ({
  credentialId,
  onBack,
  onRelogin,
  onPick,
}: {
  credentialId: string;
  onBack: () => void;
  onRelogin: () => void;
  onPick: (project: GitProject) => void;
}) => {
  const { t } = useTranslation("gitServer");
  const [q, setQ] = useState("");
  const projects = useGitServerProjects(credentialId, q);
  const code = projects.isError ? failureCode(projects.error) : null;
  return (
    <div
      className="flex flex-col"
      style={{ gap: 10 }}
      data-testid="git-server-projects"
    >
      <div className="flex items-center" style={{ gap: 8 }}>
        <button
          type="button"
          className="btn xs"
          onClick={onBack}
          data-testid="git-server-projects-back"
        >
          <ChevronLeft size={12} aria-hidden="true" />
          {t("projects.back")}
        </button>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>
          {t("projects.title")}
        </span>
      </div>
      <SearchInput
        value={q}
        onChange={setQ}
        label={t("projects.search")}
        placeholder={t("projects.search")}
        busy={projects.isFetching}
      />
      {projects.isLoading && <Spinner size="sm" />}
      {code === "auth_failed" && (
        <Notice
          tone="warn"
          role="alert"
          text={t("projects.authFailed")}
          action={
            <button type="button" className="btn xs" onClick={onRelogin}>
              {t("servers.relogin")}
            </button>
          }
        />
      )}
      {code !== null && code !== "auth_failed" && (
        <Notice tone="err" role="alert" text={t("projects.loadFailed")} />
      )}
      {projects.data?.items.length === 0 && (
        <EmptyState
          compact
          title={t("projects.empty")}
          testId="git-server-projects-empty"
        />
      )}
      {projects.data?.items.map((project) => (
        <div
          key={project.id}
          className="flex items-center"
          style={{
            gap: 12,
            padding: "10px 12px",
            borderRadius: "var(--r-2)",
            border: "1px solid var(--border)",
            background: "var(--bg-1)",
          }}
          data-testid={`git-server-project-${project.id}`}
        >
          <span
            className="flex flex-col"
            style={{ gap: 2, flex: 1, minWidth: 0 }}
          >
            <span style={{ fontWeight: 500, fontSize: 13 }}>
              {project.name}
            </span>
            <span className="dim" style={{ fontSize: 12 }}>
              {[
                t("projects.owner", { name: project.owner_name }),
                t(`projects.role.${project.role}`),
                project.can_push ? null : t("projects.readOnly"),
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </span>
          <Button
            type="button"
            onClick={() => {
              onPick(project);
            }}
            data-testid={`git-server-project-clone-${project.id}`}
          >
            {t("projects.clone")}
          </Button>
        </div>
      ))}
    </div>
  );
};
