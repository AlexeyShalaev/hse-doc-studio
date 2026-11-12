import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { MessageSquare, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { EditorView } from "@codemirror/view";
import type { Extension } from "@codemirror/state";
import {
  CommentsPanel,
  isTextThread,
  makeAnchor,
  QUOTE_MAX,
  reviewApi,
  useReviewThreads,
  type PendingThread,
} from "@entities/review";
import { toast, useIsPhoneWidth } from "@shared/lib";
import type { CodeEditorController } from "@shared/ui";
import { createReviewBridge } from "./reviewMarks";
import { useReviewMarks } from "./useReviewMarks";

export type EditorReviewOptions = {
  projectId: string;
  path: string;
  /** Серверный режим и роль в проекте: без них панели нет. */
  enabled: boolean;
  canComment: boolean;
  canModerate: boolean;
  isOwner: boolean;
  currentUserId: string | null;
  /** Идёт сессия совместной правки: треды обновляются событием сервера, а не опросом. */
  live: boolean;
  controller: RefObject<CodeEditorController | null>;
  /** Растёт с каждой правкой текста: по нему пересчитывается привязка. */
  docRevision: number;
};

export type EditorReview = {
  extensions: Extension[];
  toolbar: ReactNode;
  panel: ReactNode;
};

/** Ревью-комментарии в редакторе исходников: подсветка фрагментов, кнопка в панели инструментов и боковая панель. */
export const useEditorReview = ({
  projectId,
  path,
  enabled,
  canComment,
  canModerate,
  isOwner,
  currentUserId,
  live,
  controller,
  docRevision,
}: EditorReviewOptions): EditorReview => {
  const { t } = useTranslation("review");
  const [params, setParams] = useSearchParams();
  const [bridge] = useState(createReviewBridge);
  const [open, setOpen] = useState(false);
  const [localActive, setLocalActive] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingThread | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  const phone = useIsPhoneWidth();
  const { data } = useReviewThreads(projectId, path, { enabled, live });
  // Треды к месту в PDF живут на пути самого PDF: в редакторе исходника их нет.
  const threads = useMemo(() => (data ?? []).filter(isTextThread), [data]);

  // Ссылка из «Входящих»: ?thread=<id> открывает панель на этом треде, пока человек не выберет другое.
  // Тред не этого файла (например, к месту в PDF, открытому рядом) редактор не трогает.
  const param = enabled ? params.get("thread") : null;
  const requested =
    param !== null && threads.some((x) => x.id === param) ? param : null;
  const activeId = requested ?? localActive;
  const panelOpen = open || requested !== null;
  const resolved = useReviewMarks(
    controller,
    threads,
    activeId,
    docRevision,
    showResolved,
  );

  const dropRequested = (): void => {
    if (requested === null) return;
    const next = new URLSearchParams(params);
    next.delete("thread");
    setParams(next, { replace: true });
  };

  const select = (id: string | null): void => {
    dropRequested();
    setLocalActive(id);
    if (id !== null) setOpen(true);
  };

  const startComment = (): void => {
    const view = controller.current?.view();
    if (!view || !canComment) return;
    const { from, to } = view.state.selection.main;
    if (from === to || view.state.sliceDoc(from, to).trim() === "") {
      toast.info(t("selectFirst"));
      return;
    }
    if (to - from > QUOTE_MAX) {
      toast.info(t("quoteTooLong", { max: QUOTE_MAX }));
      return;
    }
    const anchor = makeAnchor(view.state.doc.toString(), from, to);
    setPending({
      quote: anchor.quote,
      create: (body, mentions) =>
        reviewApi.createThread(projectId, { path, anchor, body, mentions }),
    });
    setOpen(true);
  };

  useEffect(() => {
    bridge.bind({ onSelect: select, onComment: startComment });
  });

  // Выбранный тред показывается в тексте: курсор на его фрагмент.
  useEffect(() => {
    const found = activeId ? resolved.get(activeId) : undefined;
    const view = controller.current?.view();
    if (!view || !found || found.state === "lost") return;
    view.dispatch({
      selection: { anchor: found.from },
      effects: EditorView.scrollIntoView(found.from, { y: "center" }),
    });
  }, [activeId, controller, resolved]);

  const openCount = threads.filter((x) => x.status === "open").length;
  const toolbar = enabled ? (
    <>
      {canComment && (
        <button
          type="button"
          className="icon-btn sm tt"
          data-tt={t("addHint")}
          aria-label={t("add")}
          data-testid="review-add"
          onClick={startComment}
        >
          <MessageSquarePlus size="0.8125rem" />
        </button>
      )}
      <button
        type="button"
        className={`icon-btn sm tt${panelOpen ? " active" : ""}`}
        data-tt={t("count", { count: openCount })}
        aria-label={t("title")}
        aria-pressed={panelOpen}
        data-testid="review-toggle-panel"
        onClick={() => {
          if (panelOpen) dropRequested();
          setOpen(!panelOpen);
        }}
      >
        <MessageSquare size="0.8125rem" />
        {openCount > 0 && (
          <span style={{ fontSize: "0.65625rem", marginLeft: "0.125rem" }}>
            {openCount}
          </span>
        )}
      </button>
    </>
  ) : null;

  const panel =
    enabled && panelOpen ? (
      <CommentsPanel
        projectId={projectId}
        threads={threads}
        stateOf={(thread) => {
          const state = resolved.get(thread.id)?.state;
          return state && state !== "ok" ? t(`state.${state}`) : null;
        }}
        activeId={activeId}
        onActivate={select}
        pending={pending}
        onPendingDone={() => {
          setPending(null);
        }}
        showResolved={showResolved}
        onToggleResolved={() => {
          setShowResolved((v) => !v);
        }}
        canComment={canComment}
        canModerate={canModerate}
        isOwner={isOwner}
        currentUserId={currentUserId}
        sheet={phone}
        onClose={() => {
          dropRequested();
          setOpen(false);
        }}
      />
    ) : null;

  return { extensions: [bridge.extension], toolbar, panel };
};
