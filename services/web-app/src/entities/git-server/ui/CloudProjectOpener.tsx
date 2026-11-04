import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import { Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { ProgressBar } from "@shared/ui/ProgressBar";
import {
  gitErrorMessage,
  describeGitError,
  readGitError,
  useOperation,
} from "@entities/git-sync";
import { ProfileForm, useProfile } from "@entities/profile";
import { projectKeys } from "@entities/project";
import { gitServerKeys, useOpenCloudProject } from "../api/gitServerQueries";

export type CloudProjectOpenerProps = {
  credentialId: string;
  projectId: string;
  /** Проект открыт на компьютере (был или только что скачан): можно переходить в него. */
  onOpened: (projectId: string) => void;
  /** «К списку проектов» при сбое. */
  onExit: () => void;
  /** Доступ к серверу истёк: войти заново (если не передано, кнопки нет). */
  onReconnect?: (() => void) | undefined;
};

type Failure = { code: string; message: string };

type Step = "connect" | "download" | "verify" | "register";

const stepOf = (phase: string): Step =>
  phase === "download" || phase === "verify" || phase === "register"
    ? phase
    : "connect";

/**
 * Открыть облачный проект одним нажатием (docs/design/local-from-cloud.md): локальная Студия сама
 * скачивает его в стандартную папку проектов, показывает ход работы и сообщает, когда проект готов.
 * Слов «git», «клонировать» и выбора папки здесь нет; если проект уже на компьютере, скачивания нет.
 */
export const CloudProjectOpener = ({
  credentialId,
  projectId,
  onOpened,
  onExit,
  onReconnect,
}: CloudProjectOpenerProps) => {
  const { t } = useTranslation("localStudio");
  const queryClient = useQueryClient();
  const open = useOpenCloudProject();
  const [operationId, setOperationId] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const started = useRef(false);
  const finished = useRef(false);
  const operation = useOperation(operationId).data;

  const opened = useCallback(
    (id: string) => {
      if (finished.current) return;
      finished.current = true;
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      void queryClient.invalidateQueries({ queryKey: gitServerKeys.cloud() });
      onOpened(id);
    },
    [onOpened, queryClient],
  );

  const start = useCallback(() => {
    setFailure(null);
    setOperationId(null);
    open.mutate(
      { credentialId, projectId },
      {
        onSuccess: (reply) => {
          if (reply.operation_id === null) opened(reply.project_id);
          else setOperationId(reply.operation_id);
        },
        onError: (error) => {
          setFailure({
            code:
              readGitError(error)?.code ??
              (error instanceof ApiError ? error.code : "git_error"),
            message: describeGitError(error, t("cloud.open.failed")),
          });
        },
      },
    );
    // Мутация нестабильна по ссылке и не должна перезапускать открытие.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credentialId, projectId, opened, t]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
  }, [start]);

  useEffect(() => {
    if (operation?.status !== "succeeded") return;
    const result = operation.result;
    opened(result && "project_id" in result ? result.project_id : projectId);
  }, [operation, opened, projectId]);

  const operationFailure: Failure | null =
    operation?.status === "failed"
      ? {
          code: operation.error?.code ?? "git_error",
          message: gitErrorMessage(
            operation.error?.code ?? "git_error",
            operation.error?.detail ?? "",
          ),
        }
      : operation?.status === "cancelled"
        ? { code: "cancelled", message: t("cloud.open.cancelled") }
        : null;
  const problem = failure ?? operationFailure;

  if (problem?.code === "profile_required") {
    return (
      <ProfileStep
        onSaved={() => {
          started.current = true;
          start();
        }}
        onExit={onExit}
      />
    );
  }

  if (problem) {
    return (
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="cloud-open-failed"
        data-code={problem.code}
      >
        <Notice
          tone="err"
          role="alert"
          text={
            problem.code === "not_found"
              ? t("cloud.open.notFound")
              : problem.message
          }
        />
        <div
          className="flex"
          style={{ gap: "0.5rem", justifyContent: "flex-end" }}
        >
          <Button
            type="button"
            variant="ghost"
            onClick={onExit}
            data-testid="cloud-open-exit"
          >
            {t("cloud.open.toList")}
          </Button>
          {problem.code === "auth_failed" && onReconnect && (
            <Button type="button" onClick={onReconnect}>
              {t("cloud.reconnect")}
            </Button>
          )}
          {problem.code !== "auth_failed" && problem.code !== "not_found" && (
            <Button
              type="button"
              onClick={() => {
                finished.current = false;
                start();
              }}
              data-testid="cloud-open-retry"
            >
              {t("cloud.open.retry")}
            </Button>
          )}
        </div>
      </div>
    );
  }

  const step = operation ? stepOf(operation.phase) : "connect";
  const percent =
    step === "download" &&
    operation?.percent !== null &&
    operation?.percent !== undefined
      ? Math.round(operation.percent)
      : null;

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.625rem" }}
      data-testid="cloud-open-progress"
      data-step={step}
    >
      <span
        className="flex items-center dim"
        style={{ gap: "0.5rem", fontSize: "0.8125rem" }}
        role="status"
        aria-live="polite"
      >
        <Spinner size="sm" />
        {t(`cloud.open.step.${step}`)}
        {percent !== null && ` ${String(percent)}%`}
      </span>
      {percent !== null && (
        <ProgressBar percent={percent} label={t("cloud.open.step.download")} />
      )}
      <span className="dim" style={{ fontSize: "0.75rem" }}>
        {t("cloud.open.hint")}
      </span>
    </div>
  );
};

const ProfileStep = ({
  onSaved,
  onExit,
}: {
  onSaved: () => void;
  onExit: () => void;
}) => {
  const { t } = useTranslation("localStudio");
  const profile = useProfile();
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.625rem" }}
      data-testid="cloud-open-profile"
    >
      <span
        className="flex items-center"
        style={{ gap: "0.5rem", fontSize: "0.8125rem" }}
      >
        <AlertTriangle size="0.875rem" aria-hidden="true" />
        {t("cloud.open.profile")}
      </span>
      {profile.data ? (
        <ProfileForm
          profile={profile.data}
          variant="dialog"
          autoFocus
          allowUnchanged
          submitLabel={t("cloud.open.profileContinue")}
          onCancel={onExit}
          cancelLabel={t("cloud.open.toList")}
          onSaved={onSaved}
        />
      ) : (
        <Spinner size="sm" />
      )}
    </div>
  );
};
