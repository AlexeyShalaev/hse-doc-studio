import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { History, OctagonAlert, PartyPopper, X } from "lucide-react";
import {
  describeGitError,
  gitHistoryPath,
  useConflictSession,
  type ConflictSession,
} from "@entities/git-sync";
import { ApiError } from "@shared/api";
import { Spinner } from "@shared/ui/Spinner";
import { Notice, type NoticeTone } from "@shared/ui/ConflictKit";
import {
  useConflictWorkspace,
  type ConflictNotice,
} from "../model/useConflictWorkspace";
import { AbortConfirmModal } from "./AbortConfirmModal";
import { ApplyProgress } from "./ApplyProgress";
import { ConflictFileList } from "./ConflictFileList";
import { ConflictFilePane } from "./ConflictFilePane";
import { ConflictHeader } from "./ConflictHeader";
import { SyncWarnings } from "./SyncWarnings";

export type ConflictScreenProps = {
  projectId: string;
};

const isEditable = (target: EventTarget): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  );
};

const NOTICE_TONE: Record<ConflictNotice["kind"], NoticeTone> = {
  outdated: "warn",
  restarted: "warn",
  unresolved: "err",
  error: "err",
};

const CenteredState = ({ children }: { children: React.ReactNode }) => (
  <div
    className="flex flex-col items-center justify-center"
    style={{
      flex: 1,
      gap: 12,
      padding: 32,
      textAlign: "center",
      minHeight: 280,
    }}
  >
    {children}
  </div>
);

const NoticeBar = ({
  notice,
  onDismiss,
}: {
  notice: ConflictNotice;
  onDismiss: () => void;
}) => {
  const { t } = useTranslation("gitConflicts");
  const text = ((): string => {
    switch (notice.kind) {
      case "unresolved":
        return t("notice.unresolved", { count: notice.count });
      case "error":
        return notice.message;
      default:
        return t(`notice.${notice.kind}`);
    }
  })();
  return (
    <div className="conflict-notice">
      <Notice
        tone={NOTICE_TONE[notice.kind]}
        role={notice.kind === "error" ? "alert" : "status"}
        text={text}
        action={
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("notice.dismiss")}
            onClick={onDismiss}
          >
            <X size={12} aria-hidden="true" />
          </button>
        }
      />
    </div>
  );
};

type WorkspaceViewProps = {
  projectId: string;
  session: ConflictSession;
};

/** Экран с загруженным сеансом: шапка, список файлов, разбор выбранного файла. */
const ConflictWorkspaceView = ({ projectId, session }: WorkspaceViewProps) => {
  const { t } = useTranslation("gitConflicts");
  const workspace = useConflictWorkspace(projectId, session);
  const [abortOpen, setAbortOpen] = useState(false);
  const { completion } = workspace;

  // N и Shift+N: к следующему и предыдущему нерешённому месту, откуда бы ни
  // вызвали, кроме полей ввода.
  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey) return;
    if (event.altKey || event.key.toLowerCase() !== "n") return;
    if (isEditable(event.target) || completion.kind !== "idle") return;
    // События из окна подтверждения (оно в портале) сюда тоже всплывают.
    if (
      !(event.target instanceof Node) ||
      !event.currentTarget.contains(event.target)
    ) {
      return;
    }
    event.preventDefault();
    workspace.jumpHunk(event.shiftKey ? -1 : 1);
  };

  return (
    <section
      className="conflict-screen"
      aria-label={t("title")}
      onKeyDown={handleKeyDown}
    >
      <ConflictHeader
        session={session}
        progress={workspace.progress}
        saveState={workspace.drafts.saveState}
        canComplete={workspace.canComplete}
        isBusy={completion.kind !== "idle" || workspace.isAborting}
        isCompleting={completion.kind === "running"}
        onComplete={() => {
          void workspace.complete();
        }}
        onAbort={() => {
          setAbortOpen(true);
        }}
        onRetrySave={() => {
          void workspace.drafts.flush();
        }}
      />

      {workspace.notice && completion.kind === "idle" && (
        <NoticeBar
          notice={workspace.notice}
          onDismiss={workspace.dismissNotice}
        />
      )}

      {completion.kind === "idle" && (
        <SyncWarnings warnings={session.warnings} />
      )}

      {completion.kind !== "idle" ? (
        <div className="conflict-apply">
          <ApplyProgress
            completion={completion}
            isCancelling={workspace.isCancelling}
            onCancel={workspace.cancelCompletion}
            onRetry={() => {
              void workspace.retryCompletion();
            }}
            onBack={workspace.dismissCompletion}
            onOpenHistory={workspace.openHistory}
          />
        </div>
      ) : (
        <div className="conflict-body">
          <div className="conflict-list">
            <ConflictFileList
              needs={workspace.needs}
              auto={workspace.auto}
              selectedPath={workspace.selected?.path ?? null}
              drafts={workspace.drafts.drafts}
              progressOf={workspace.progressOf}
              onSelect={workspace.selectFile}
            />
          </div>
          <div className="conflict-pane">
            <ConflictFilePane projectId={projectId} workspace={workspace} />
          </div>
        </div>
      )}

      <AbortConfirmModal
        isOpen={abortOpen}
        isPending={workspace.isAborting}
        versionName={session.ours.message ?? null}
        onClose={() => {
          setAbortOpen(false);
        }}
        onConfirm={() => {
          void workspace.abort().finally(() => {
            setAbortOpen(false);
          });
        }}
      />
    </section>
  );
};

/** Полноэкранный разбор конфликтов синхронизации. */
export const ConflictScreen = ({ projectId }: ConflictScreenProps) => {
  const { t } = useTranslation("gitConflicts");
  const navigate = useNavigate();
  const {
    data: session,
    error,
    isLoading,
    refetch,
  } = useConflictSession(projectId);

  // Сеанса нет: синхронизация завершена или слияние отменено. Проверка идёт
  // раньше показа сеанса: react-query хранит прежние данные и после ответа 404.
  const gone = error instanceof ApiError && error.status === 404;

  if (session && !gone) {
    return <ConflictWorkspaceView projectId={projectId} session={session} />;
  }

  if (isLoading) {
    return (
      <CenteredState>
        <div role="status" className="flex items-center" style={{ gap: 8 }}>
          <Spinner size="sm" />
          <span className="dim" style={{ fontSize: 12.5 }}>
            {t("state.loading")}
          </span>
        </div>
      </CenteredState>
    );
  }

  if (gone) {
    return (
      <CenteredState>
        <PartyPopper
          size={32}
          aria-hidden="true"
          style={{ color: "var(--c-ok)" }}
        />
        <h2 style={{ margin: 0, fontSize: 16 }}>{t("state.none.title")}</h2>
        <p className="dim" style={{ margin: 0, fontSize: 12.5, maxWidth: 420 }}>
          {t("state.none.text")}
        </p>
        <button
          type="button"
          className="btn"
          onClick={() => {
            void navigate(gitHistoryPath(projectId));
          }}
        >
          <History size={13} aria-hidden="true" />
          {t("state.none.back")}
        </button>
      </CenteredState>
    );
  }

  return (
    <CenteredState>
      <OctagonAlert
        size={32}
        aria-hidden="true"
        style={{ color: "var(--c-err)" }}
      />
      <h2 style={{ margin: 0, fontSize: 16 }}>{t("state.error.title")}</h2>
      <p
        role="alert"
        className="dim"
        style={{ margin: 0, fontSize: 12.5, maxWidth: 480 }}
      >
        {describeGitError(error, t("state.error.text"))}
      </p>
      <button
        type="button"
        className="btn"
        onClick={() => {
          void refetch();
        }}
      >
        {t("state.retry")}
      </button>
    </CenteredState>
  );
};
