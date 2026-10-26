import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import {
  gitErrorMessage,
  useCancelOperation,
  useOperation,
  type CloneResult,
  type GitOperation,
} from "@entities/git-sync";
import { projectKeys } from "@entities/project";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { Stepper, type StepState, type StepperStep } from "@shared/ui/Stepper";
import { isCloneAccess, type CloneAccess } from "../../model/cloneVerdict";
import { cloneFailureTarget } from "../../model/cloneFailure";
import { Btn, Facts, ResultFrame } from "../ResultFrame";
import { CloneStepLayout } from "./CloneStepLayout";

export type CloneProgressStepProps = {
  operationId: string;
  /** Клонируем из файла: у первого шага другое название. */
  fromBundle: boolean;
  onOpenProject: (projectId: string) => void;
  onToList: () => void;
  /** Вернуться к выбору папки (отмена, отказ, «Попробовать снова»). */
  onBackToFolder: (message: string | null) => void;
  onBackToSource: (message: { code: string; message: string }) => void;
  onProfile: () => void;
};

const STEP_IDS = ["connect", "download", "verify", "register"] as const;
type StepId = (typeof STEP_IDS)[number];

const stepOfPhase = (phase: string): StepId => {
  if (phase === "download" || phase === "verify" || phase === "register")
    return phase;
  // «В очереди» и всё, что раньше загрузки, это подключение.
  return "connect";
};

const isCloneResult = (result: GitOperation["result"]): result is CloneResult =>
  result !== null && result !== undefined && "project_id" in result;

const ProgressBar = ({
  percent,
  label,
}: {
  percent: number;
  label: string;
}) => (
  <div
    role="progressbar"
    aria-label={label}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={Math.round(percent)}
    style={{
      height: 6,
      borderRadius: 999,
      background: "var(--bg-3)",
      overflow: "hidden",
    }}
  >
    <div
      style={{
        width: `${String(Math.min(100, Math.max(0, percent)))}%`,
        height: "100%",
        borderRadius: 999,
        background: "var(--accent)",
        transition: "width 300ms ease",
      }}
    />
  </div>
);

// Шаг 3. Клонирование идёт на стороне Студии: окно показывает фазы и процент,
// даёт отменить и в конце либо открывает проект, либо объясняет, что не вышло и
// что исправить.
export const CloneProgressStep = ({
  operationId,
  fromBundle,
  onOpenProject,
  onToList,
  onBackToFolder,
  onBackToSource,
  onProfile,
}: CloneProgressStepProps) => {
  const { t } = useTranslation("gitRemote");
  const queryClient = useQueryClient();
  const operationQuery = useOperation(operationId);
  const cancel = useCancelOperation();
  const operation = operationQuery.data;
  const finishedRef = useRef(false);

  // Новый проект сразу виден в списке, не дожидаясь перечитывания.
  useEffect(() => {
    if (operation?.status === "succeeded" && !finishedRef.current) {
      finishedRef.current = true;
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    }
  }, [operation?.status, queryClient]);

  if (!operation) {
    if (operationQuery.isError) {
      return (
        <CloneStepLayout
          id="clone-progress"
          aria-label={t("clone.steps.progress")}
          start={
            <button type="button" className="btn" onClick={onToList}>
              {t("clone.progress.done.toList")}
            </button>
          }
        >
          <ResultFrame
            tone="warn"
            role="alert"
            title={t("clone.progress.lost.title")}
            testId="clone-progress-lost"
            actions={
              <Btn
                primary
                onClick={() => {
                  void operationQuery.refetch();
                }}
              >
                {t("clone.progress.lost.retry")}
              </Btn>
            }
          >
            <p style={{ margin: 0 }}>{t("clone.progress.lost.text")}</p>
          </ResultFrame>
        </CloneStepLayout>
      );
    }
    return (
      <CloneStepLayout
        id="clone-progress"
        aria-label={t("clone.steps.progress")}
      >
        <div
          role="status"
          className="flex items-center dim"
          style={{ gap: 8, minHeight: 120, justifyContent: "center" }}
        >
          <Spinner size="sm" />
          {t("clone.progress.starting")}
        </div>
      </CloneStepLayout>
    );
  }

  const current = stepOfPhase(operation.phase);
  const currentIndex = STEP_IDS.indexOf(current);
  const percent =
    operation.status === "running" &&
    current === "download" &&
    operation.percent !== null &&
    operation.percent !== undefined
      ? operation.percent
      : null;

  const stateOf = (index: number): StepState => {
    if (operation.status === "succeeded") return "done";
    if (operation.status === "failed")
      return index < currentIndex
        ? "done"
        : index === currentIndex
          ? "error"
          : "upcoming";
    if (operation.status === "cancelled")
      return index < currentIndex ? "done" : "upcoming";
    return index < currentIndex
      ? "done"
      : index === currentIndex
        ? "current"
        : "upcoming";
  };

  const steps: StepperStep[] = STEP_IDS.map((id, index) => ({
    id,
    label:
      id === "download" && fromBundle
        ? t("clone.progress.phase.downloadBundle")
        : t(`clone.progress.phase.${id}`),
    state: stateOf(index),
    ...(id === current && percent !== null
      ? { meta: `${String(Math.round(percent))}%` }
      : {}),
    ...(id === current && operation.status === "running" && operation.message
      ? { description: operation.message }
      : {}),
  }));

  const stepper = (
    <div aria-live="polite" data-testid="clone-phases">
      <Stepper
        steps={steps}
        current={current}
        busy={operation.status === "running"}
        orientation="vertical"
        label={t("clone.progress.label")}
      />
    </div>
  );

  // --- идёт ----------------------------------------------------------------
  if (operation.status === "running") {
    const cancelRefused =
      cancel.error instanceof ApiError &&
      cancel.error.code === "operation_not_cancellable";
    return (
      <CloneStepLayout
        id="clone-progress"
        aria-label={t("clone.steps.progress")}
        end={
          <button
            type="button"
            className="btn"
            disabled={!operation.cancellable || cancel.isPending}
            onClick={() => {
              cancel.mutate(operation.id);
            }}
          >
            {cancel.isPending && <Spinner size="sm" />}
            {cancel.isPending
              ? t("clone.progress.cancelling")
              : t("clone.progress.cancel")}
          </button>
        }
      >
        <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
          {t("clone.lead.progress")}
        </p>
        {stepper}
        {percent !== null && (
          <ProgressBar
            percent={percent}
            label={t("clone.progress.phase.download")}
          />
        )}
        {cancelRefused && (
          <Notice
            tone="info"
            role="status"
            text={t("clone.progress.cancelFailed")}
          />
        )}
      </CloneStepLayout>
    );
  }

  // --- отменено --------------------------------------------------------------
  if (operation.status === "cancelled") {
    return (
      <CloneStepLayout
        id="clone-progress"
        aria-label={t("clone.steps.progress")}
        start={
          <button type="button" className="btn" onClick={onToList}>
            {t("clone.progress.done.toList")}
          </button>
        }
      >
        {stepper}
        <ResultFrame
          tone="info"
          role="status"
          title={t("clone.progress.cancelled.title")}
          testId="clone-progress-cancelled"
          actions={
            <Btn
              primary
              onClick={() => {
                onBackToFolder(null);
              }}
            >
              {t("clone.progress.cancelled.again")}
            </Btn>
          }
        >
          <p style={{ margin: 0 }}>{t("clone.progress.cancelled.text")}</p>
        </ResultFrame>
      </CloneStepLayout>
    );
  }

  // --- не удалось ------------------------------------------------------------
  if (operation.status === "failed") {
    const code = operation.error?.code ?? "git_error";
    const detail = operation.error?.detail ?? "";
    const message = gitErrorMessage(code, detail);
    const target = cloneFailureTarget(code);
    const action =
      target === "folder"
        ? {
            label: t("clone.progress.failed.folder"),
            run: () => {
              onBackToFolder(message);
            },
          }
        : target === "source"
          ? {
              label: t("clone.progress.failed.source"),
              run: () => {
                onBackToSource({ code, message });
              },
            }
          : target === "profile"
            ? { label: t("clone.progress.failed.profile"), run: onProfile }
            : {
                label: t("clone.progress.failed.retry"),
                run: () => {
                  onBackToFolder(null);
                },
              };
    return (
      <CloneStepLayout
        id="clone-progress"
        aria-label={t("clone.steps.progress")}
        start={
          <button type="button" className="btn" onClick={onToList}>
            {t("clone.progress.done.toList")}
          </button>
        }
      >
        {stepper}
        <ResultFrame
          tone="err"
          role="alert"
          title={t("clone.progress.failed.title")}
          testId={`clone-progress-failed-${code}`}
          actions={
            <Btn primary onClick={action.run}>
              {action.label}
            </Btn>
          }
        >
          <p style={{ margin: 0 }}>{message}</p>
          {detail !== "" && detail !== message && (
            <details className="sync-details">
              <summary>{t("issue.details")}</summary>
              <pre
                className="mono"
                style={{
                  margin: "6px 0 0",
                  fontSize: 11,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  color: "var(--fg-2)",
                }}
              >
                {detail}
              </pre>
            </details>
          )}
        </ResultFrame>
      </CloneStepLayout>
    );
  }

  // --- готово ------------------------------------------------------------
  const result = isCloneResult(operation.result) ? operation.result : null;
  const projectId = result?.project_id ?? operation.project_id ?? null;
  const access: CloneAccess =
    result && isCloneAccess(result.access) ? result.access : "full";
  const full = access === "full";
  const facts: [string, string][] = [];
  if (result) {
    facts.push([t("clone.progress.done.folder"), result.folder]);
    facts.push([
      t("clone.progress.done.access"),
      t(`clone.progress.access.${access}`),
    ]);
  }
  const lfs = result?.warnings.find((w) => w.code === "lfs_pointers");

  return (
    <CloneStepLayout
      id="clone-progress"
      aria-label={t("clone.steps.progress")}
      start={
        <button type="button" className="btn" onClick={onToList}>
          {t("clone.progress.done.toList")}
        </button>
      }
      end={
        projectId ? (
          <button
            type="button"
            className="btn primary"
            autoFocus
            onClick={() => {
              onOpenProject(projectId);
            }}
          >
            {t("clone.progress.done.open")}
          </button>
        ) : undefined
      }
    >
      {stepper}
      <ResultFrame
        tone={full ? "ok" : "warn"}
        role="status"
        title={t("clone.progress.done.title")}
        testId="clone-progress-done"
      >
        <p style={{ margin: 0 }}>{t("clone.progress.done.text")}</p>
        {facts.length > 0 && <Facts items={facts} />}
        {access !== "full" && (
          <Notice
            tone="warn"
            role="status"
            text={
              result?.required_studio
                ? `${t(`clone.source.verdict.${access}`)} ${t("result.warn.schemaNewerVersion", { version: result.required_studio })}`
                : t(`clone.source.verdict.${access}`)
            }
          />
        )}
        {result?.warnings.some((w) => w.code === "template_missing") && (
          <Notice
            tone="warn"
            role="status"
            text={t("clone.progress.warn.template_missing")}
          />
        )}
        {lfs && (
          <Notice
            tone="warn"
            role="status"
            text={t("clone.progress.warn.lfs_pointers")}
          />
        )}
      </ResultFrame>
    </CloneStepLayout>
  );
};
