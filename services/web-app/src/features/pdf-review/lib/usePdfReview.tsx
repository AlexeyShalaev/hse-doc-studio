import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { FileCode2, MessageSquare } from "lucide-react";
import {
  CommentsPanel,
  QUOTE_MAX,
  reviewApi,
  useDocumentReview,
  type PendingThread,
  type PlacedThread,
  type ReviewThread,
} from "@entities/review";
import { toast, useIsPhoneWidth } from "@shared/lib";
import type { PdfMark, PdfSelection } from "@shared/ui";

export type PdfReviewOptions = {
  projectId: string;
  docId: string;
  /** Серверный режим и роль в проекте: без них комментариев в превью нет. */
  enabled: boolean;
  canComment: boolean;
  canModerate: boolean;
  isOwner: boolean;
  currentUserId: string | null;
};

/** Что превью передаёт просмотрщику PDF: кнопка на выделении, метки и переход к метке. */
export type PdfReviewViewer = {
  onComment?: (selection: PdfSelection) => void;
  marks: PdfMark[];
  onMarkClick: (id: string) => void;
  onMarksPlaced: (placed: Record<string, boolean>) => void;
  focusMark: { id: string; token: number } | null;
};

export type PdfReview = {
  viewer: PdfReviewViewer;
  toolbar: ReactNode;
  panel: ReactNode;
};

/**
 * Комментарии в превью PDF (stage5-review-realtime.md, 2.4): «Комментировать» на
 * выделении, метки на полях страниц, подсветка фрагмента выбранного треда и та же
 * панель «Комментарии», что в редакторе (на телефоне шторкой снизу).
 */
export const usePdfReview = ({
  projectId,
  docId,
  enabled,
  canComment,
  canModerate,
  isOwner,
  currentUserId,
}: PdfReviewOptions): PdfReview => {
  const { t } = useTranslation("review");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const phone = useIsPhoneWidth();
  const [open, setOpen] = useState(false);
  const [localActive, setLocalActive] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingThread | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  const [placedIds, setPlacedIds] = useState<Record<string, boolean>>({});
  const [focusToken, setFocusToken] = useState(0);
  const { data } = useDocumentReview(projectId, docId, { enabled });
  const items = useMemo<PlacedThread[]>(() => data?.items ?? [], [data]);
  const threads = useMemo(() => items.map((i) => i.thread), [items]);

  // Ссылка из «Входящих» на тред к месту в PDF: ?thread=<id> открывает панель на нём.
  const param = enabled ? params.get("thread") : null;
  const requested =
    param !== null && items.some((i) => i.thread.id === param) ? param : null;
  const activeId = requested ?? localActive;
  const panelOpen = enabled && (open || requested !== null || pending !== null);

  const dropRequested = (): void => {
    if (requested === null) return;
    const next = new URLSearchParams(params);
    next.delete("thread");
    setParams(next, { replace: true });
  };

  const select = (id: string | null): void => {
    dropRequested();
    setLocalActive(id);
    if (id !== null) {
      setOpen(true);
      setFocusToken((n) => n + 1);
    }
  };

  const onComment = (selection: PdfSelection): void => {
    if (selection.text.length > QUOTE_MAX) {
      toast.info(t("quoteTooLong", { max: QUOTE_MAX }));
      return;
    }
    setPending({
      quote: selection.text,
      create: (body, mentions) =>
        reviewApi.createPdfThread(projectId, {
          doc_id: docId,
          page: selection.page,
          rects: selection.rects,
          text: selection.text,
          body,
          mentions,
        }),
    });
    setOpen(true);
  };

  const onCreated = (thread: ReviewThread): void => {
    if (thread.anchor.kind === "text")
      toast.success(t("pdf.attachedSource", { file: thread.path }));
    else toast.info(t("pdf.attachedPdf"));
  };

  const marks = useMemo<PdfMark[]>(
    () =>
      items.flatMap(({ thread, place }) => {
        if (!place) return [];
        const resolved = thread.status === "resolved";
        if (resolved && !showResolved && thread.id !== activeId) return [];
        return [
          {
            id: thread.id,
            page: place.page,
            rects: place.rects,
            text: place.text,
            exact: place.exact,
            // Строка SyncTeX текущей сборки годится и без точного места; прежнее место PDF-треда нет.
            fallback: thread.anchor.kind === "text",
            active: thread.id === activeId,
            resolved,
            title: t(resolved ? "pdf.markTitleResolved" : "pdf.markTitle", {
              name: thread.created_by_name,
            }),
          },
        ];
      }),
    [items, showResolved, activeId, t],
  );

  const stateOf = (thread: ReviewThread): string | null => {
    const place = items.find((i) => i.thread.id === thread.id)?.place;
    if (!place) return t("pdf.placeMissing");
    if (placedIds[thread.id] === false)
      return thread.anchor.kind === "pdf"
        ? t("pdf.placeChanged")
        : t("pdf.placeMissing");
    return null;
  };

  const details = (thread: ReviewThread): ReactNode => {
    if (thread.anchor.kind === "pdf")
      return (
        <span className="dim" style={{ fontSize: "0.6875rem" }}>
          {t("pdf.inPdf", { page: thread.anchor.page })}
        </span>
      );
    const target = `/projects/${encodeURIComponent(projectId)}/files?${new URLSearchParams({ file: thread.path, thread: thread.id }).toString()}`;
    return (
      <div
        className="flex items-center"
        style={{ gap: "0.375rem", fontSize: "0.6875rem", minWidth: 0 }}
      >
        <span
          className="dim mono truncate"
          style={{ minWidth: 0, flex: 1 }}
          title={thread.path}
        >
          {t("pdf.inSource", { file: thread.path })}
        </span>
        <button
          type="button"
          className="btn xs ghost shrink-0"
          data-testid={`pdf-review-open-source-${thread.id}`}
          onClick={() => {
            void navigate(target);
          }}
        >
          <FileCode2 size="0.6875rem" />
          {t("pdf.openSource")}
        </button>
      </div>
    );
  };

  const openCount = threads.filter((x) => x.status === "open").length;
  const toolbar = enabled ? (
    <button
      type="button"
      className={`btn xs shrink-0 tt${panelOpen ? " active" : ""}`}
      data-tt={t("count", { count: openCount })}
      aria-label={t("title")}
      aria-pressed={panelOpen}
      data-testid="pdf-review-toggle"
      onClick={() => {
        if (panelOpen) {
          dropRequested();
          setPending(null);
        }
        setOpen(!panelOpen);
      }}
    >
      <MessageSquare size="0.6875rem" />
      {phone ? null : t("title")}
      {openCount > 0 && <span className="mono">{openCount}</span>}
    </button>
  ) : null;

  const panel = panelOpen ? (
    <CommentsPanel
      projectId={projectId}
      threads={threads}
      stateOf={stateOf}
      details={details}
      activeId={activeId}
      onActivate={select}
      pending={pending}
      onPendingDone={() => {
        setPending(null);
      }}
      onCreated={onCreated}
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
        setPending(null);
        setOpen(false);
      }}
    />
  ) : null;

  const viewer: PdfReviewViewer = {
    marks: enabled ? marks : [],
    onMarkClick: select,
    onMarksPlaced: setPlacedIds,
    focusMark: activeId ? { id: activeId, token: focusToken } : null,
    ...(enabled && canComment ? { onComment } : {}),
  };

  return { viewer, toolbar, panel };
};
