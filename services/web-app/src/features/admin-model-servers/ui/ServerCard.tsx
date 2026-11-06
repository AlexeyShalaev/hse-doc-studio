import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Badge, Button, ConfirmByName, ProgressBar } from "@shared/ui";
import { useServerAction, useServerLogs } from "../api/queries";
import type { ModelServer } from "../api/schemas";

const STATUS_VARIANT = {
  installing: "info",
  running: "success",
  stopped: "default",
  failed: "error",
} as const;

const STEP_ORDER = ["container", "engine", "model", "provider", "verify"];

/** Один установленный сервер: статус, шаги, ход загрузки, запуск и остановка, журнал, удаление. */
export const ServerCard = ({ server }: { server: ModelServer }) => {
  const { t } = useTranslation("adminModelServers");
  const [showLogs, setShowLogs] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const action = useServerAction();
  const logs = useServerLogs(server.id, showLogs);
  const installing = server.status === "installing";
  const error = action.isError ? failureCode(action.error) : null;
  const verifyWarn =
    server.status === "running" && server.steps.verify === "failed";

  return (
    <li
      className="card"
      data-testid={`ms-server-${server.id}`}
      style={{ padding: "0.75rem 1rem", display: "grid", gap: "0.5rem" }}
    >
      <div className="flex flex-wrap items-center" style={{ gap: "0.5rem" }}>
        <strong style={{ overflowWrap: "anywhere" }}>{server.name}</strong>
        <Badge variant={STATUS_VARIANT[server.status]}>
          {t(`status.${server.status}`)}
        </Badge>
        <Badge>{t(`engine.${server.engine}`)}</Badge>
      </div>
      <div
        className="dim"
        style={{ fontSize: "0.875rem", overflowWrap: "anywhere" }}
      >
        {server.model}
      </div>
      {installing && (
        <div data-testid={`ms-progress-${server.id}`}>
          <ProgressBar percent={server.percent} label={t("progress.label")} />
          <ol
            className="flex flex-wrap"
            style={{
              gap: "0.5rem",
              listStyle: "none",
              padding: 0,
              margin: "0.5rem 0 0",
            }}
          >
            {STEP_ORDER.map((step) => (
              <li
                key={step}
                data-state={server.steps[step] ?? "pending"}
                className="dim"
                style={{ fontSize: "0.75rem" }}
              >
                {t(`step.${step}`)}:{" "}
                {t(`stepState.${server.steps[step] ?? "pending"}`)}
              </li>
            ))}
          </ol>
          {server.text && (
            <p
              className="dim"
              style={{
                margin: "0.25rem 0 0",
                fontSize: "0.75rem",
                overflowWrap: "anywhere",
              }}
            >
              {server.text}
            </p>
          )}
        </div>
      )}
      {server.error && (
        <p role="alert" className="form-hint" style={{ margin: 0 }}>
          {server.error}
        </p>
      )}
      {verifyWarn && (
        <p className="dim" style={{ margin: 0, fontSize: "0.875rem" }}>
          {t("server.notResponding")}
        </p>
      )}
      {server.status === "running" && server.provider_id && (
        <p className="dim" style={{ margin: 0, fontSize: "0.875rem" }}>
          {t("server.registered")}
        </p>
      )}
      <div className="flex flex-wrap" style={{ gap: "0.5rem" }}>
        {server.status === "running" && (
          <Button
            size="sm"
            variant="ghost"
            disabled={action.isPending}
            onClick={() => {
              action.mutate({ id: server.id, action: "stop" });
            }}
          >
            {t("server.stop")}
          </Button>
        )}
        {server.status === "stopped" && (
          <Button
            size="sm"
            disabled={action.isPending}
            onClick={() => {
              action.mutate({ id: server.id, action: "start" });
            }}
          >
            {t("server.start")}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          data-testid={`ms-logs-${server.id}`}
          onClick={() => {
            setShowLogs(!showLogs);
          }}
        >
          {showLogs ? t("server.hideLogs") : t("server.showLogs")}
        </Button>
        {!installing && (
          <Button
            size="sm"
            variant="ghost"
            data-testid={`ms-remove-${server.id}`}
            onClick={() => {
              setConfirm(true);
            }}
          >
            {t("server.remove")}
          </Button>
        )}
      </div>
      {error && (
        <span className="form-hint" role="alert">
          {t(`error.${error}`, { defaultValue: t("error.generic") })}
        </span>
      )}
      {showLogs && (
        <pre
          data-testid={`ms-logtext-${server.id}`}
          style={{
            margin: 0,
            maxHeight: "16rem",
            overflow: "auto",
            fontSize: "0.75rem",
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
          }}
        >
          {logs.data ?? t("server.logsLoading")}
        </pre>
      )}
      <ConfirmByName
        isOpen={confirm}
        onClose={() => {
          setConfirm(false);
        }}
        name={server.name}
        title={t("remove.title")}
        description={t("remove.description")}
        confirmLabel={t("remove.confirm")}
        pending={action.isPending}
        onConfirm={() => {
          action.mutate(
            { id: server.id, action: "remove", purge: false },
            {
              onSuccess: () => {
                setConfirm(false);
              },
            },
          );
        }}
      />
    </li>
  );
};
