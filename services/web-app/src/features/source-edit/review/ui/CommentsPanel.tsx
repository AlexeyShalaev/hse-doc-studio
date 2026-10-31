import { useEffect, useRef, useState } from "react";
import { Check, MessageSquare, RotateCcw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@shared/api";
import { formatRelativeTime } from "@shared/lib";
import {
  useCreateThread,
  useDeleteComment,
  useEditComment,
  useReplyToThread,
  useSetThreadStatus,
  type Anchor,
  type ResolvedAnchor,
  type ReviewComment,
  type ReviewThread,
} from "@entities/review";
import { splitMentions } from "../lib/mentions";
import { CommentComposer } from "./CommentComposer";

export type PendingThread = { anchor: Anchor };

export type CommentsPanelProps = {
  projectId: string;
  path: string;
  threads: ReviewThread[];
  resolved: Map<string, ResolvedAnchor>;
  activeId: string | null;
  onActivate: (id: string | null) => void;
  pending: PendingThread | null;
  onPendingDone: () => void;
  showResolved: boolean;
  onToggleResolved: () => void;
  canComment: boolean;
  /** Правит файл: может закрывать чужие треды. */
  canModerate: boolean;
  /** Владелец проекта: удаляет чужие комментарии. */
  isOwner: boolean;
  currentUserId: string | null;
  onClose: () => void;
};

const useFailure = () => {
  const { t } = useTranslation("review");
  return (error: unknown): string =>
    error instanceof ApiError &&
    t(`error.${error.code}`, { defaultValue: "" }) !== ""
      ? t(`error.${error.code}`)
      : t("error.generic");
};

const Body = ({ text }: { text: string }) => (
  <p
    style={{
      margin: 0,
      fontSize: 12.5,
      whiteSpace: "pre-wrap",
      overflowWrap: "anywhere",
    }}
  >
    {splitMentions(text).map((part, index) =>
      part.mention ? (
        <strong key={index} style={{ color: "var(--accent)" }}>
          {part.text}
        </strong>
      ) : (
        <span key={index}>{part.text}</span>
      ),
    )}
  </p>
);

type CommentRowProps = {
  projectId: string;
  comment: ReviewComment;
  own: boolean;
  mayDelete: boolean;
  root: boolean;
};

const CommentRow = ({
  projectId,
  comment,
  own,
  mayDelete,
  root,
}: CommentRowProps) => {
  const { t } = useTranslation("review");
  const failure = useFailure();
  const [editing, setEditing] = useState(false);
  const edit = useEditComment(projectId);
  const remove = useDeleteComment(projectId);
  return (
    <div
      className="flex flex-col"
      style={{ gap: 4 }}
      data-testid={`review-comment-${comment.id}`}
    >
      <div className="flex items-center" style={{ gap: 6, fontSize: 11.5 }}>
        <strong>{comment.author_name}</strong>
        <span className="dim">{formatRelativeTime(comment.created_at)}</span>
        {comment.edited_at && <span className="dim">({t("edited")})</span>}
        <span style={{ flex: 1 }} />
        {own && !editing && (
          <button
            type="button"
            className="btn xs ghost"
            onClick={() => {
              setEditing(true);
            }}
          >
            {t("edit")}
          </button>
        )}
        {mayDelete && !editing && (
          <button
            type="button"
            className="btn xs ghost"
            disabled={remove.isPending}
            onClick={() => {
              if (
                window.confirm(
                  root ? t("deleteThreadConfirm") : t("deleteConfirm"),
                )
              ) {
                remove.mutate(comment.id);
              }
            }}
          >
            {t("delete")}
          </button>
        )}
      </div>
      {editing ? (
        <CommentComposer
          projectId={projectId}
          placeholder={t("placeholder")}
          submitLabel={t("send")}
          initialText={comment.body}
          busy={edit.isPending}
          error={edit.isError ? failure(edit.error) : null}
          autoFocus
          onSubmit={(body) => {
            edit.mutate(
              { commentId: comment.id, body },
              {
                onSuccess: () => {
                  setEditing(false);
                },
              },
            );
          }}
          onCancel={() => {
            setEditing(false);
          }}
        />
      ) : (
        <Body text={comment.body} />
      )}
      {remove.isError && (
        <span role="alert" style={{ color: "var(--c-err)", fontSize: 11.5 }}>
          {failure(remove.error)}
        </span>
      )}
    </div>
  );
};

type ThreadCardProps = Pick<
  CommentsPanelProps,
  "projectId" | "canComment" | "canModerate" | "isOwner" | "currentUserId"
> & {
  thread: ReviewThread;
  state: ResolvedAnchor["state"] | undefined;
  active: boolean;
  onActivate: () => void;
};

const ThreadCard = ({
  projectId,
  thread,
  state,
  active,
  canComment,
  canModerate,
  isOwner,
  currentUserId,
  onActivate,
}: ThreadCardProps) => {
  const { t } = useTranslation("review");
  const failure = useFailure();
  const ref = useRef<HTMLElement>(null);
  const reply = useReplyToThread(projectId);
  const status = useSetThreadStatus(projectId);
  const done = thread.status === "resolved";
  const mayToggle =
    canComment && (thread.created_by === currentUserId || canModerate);

  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest" });
  }, [active]);

  return (
    <section
      ref={ref}
      data-testid={`review-thread-${thread.id}`}
      data-status={thread.status}
      data-active={active}
      style={{
        padding: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        borderRadius: "var(--r-2)",
        border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
        background: done ? "var(--bg-2)" : "var(--bg-1)",
        opacity: done && !active ? 0.8 : 1,
      }}
    >
      <button
        type="button"
        className="mono"
        title={t("goTo")}
        onClick={onActivate}
        style={{
          textAlign: "left",
          fontSize: 11.5,
          padding: "2px 6px",
          background: "var(--bg-2)",
          border: 0,
          borderLeft: "3px solid var(--c-warn)",
          color: "var(--fg-1)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {thread.anchor.quote.replace(/\s+/g, " ")}
      </button>
      {state && state !== "ok" && (
        <span
          className="dim"
          style={{ fontSize: 11 }}
          data-testid="review-anchor-state"
        >
          {t(`state.${state}`)}
        </span>
      )}
      {thread.comments.map((comment, index) => (
        <CommentRow
          key={comment.id}
          projectId={projectId}
          comment={comment}
          own={
            canComment &&
            comment.author_id !== null &&
            comment.author_id === currentUserId
          }
          mayDelete={
            canComment &&
            ((comment.author_id !== null &&
              comment.author_id === currentUserId) ||
              isOwner)
          }
          root={index === 0}
        />
      ))}
      {done && thread.resolved_by_name && (
        <span className="dim" style={{ fontSize: 11 }}>
          {t("resolvedBy", { name: thread.resolved_by_name })}
        </span>
      )}
      {canComment && !done && (
        <CommentComposer
          projectId={projectId}
          placeholder={t("replyPlaceholder")}
          submitLabel={t("reply")}
          busy={reply.isPending}
          error={reply.isError ? failure(reply.error) : null}
          onSubmit={(body, mentions) => {
            reply.mutate({ threadId: thread.id, body, mentions });
          }}
        />
      )}
      {mayToggle && (
        <div className="flex" style={{ justifyContent: "flex-end" }}>
          <button
            type="button"
            className="btn xs"
            disabled={status.isPending}
            data-testid={`review-toggle-${thread.id}`}
            onClick={() => {
              status.mutate({
                threadId: thread.id,
                status: done ? "open" : "resolved",
              });
            }}
          >
            {done ? <RotateCcw size={11} /> : <Check size={11} />}
            {done ? t("reopen") : t("resolve")}
          </button>
        </div>
      )}
      {status.isError && (
        <span role="alert" style={{ color: "var(--c-err)", fontSize: 11.5 }}>
          {failure(status.error)}
        </span>
      )}
    </section>
  );
};

/** Панель «Комментарии» справа от текста: новый комментарий к выделению и треды файла. */
export const CommentsPanel = (props: CommentsPanelProps) => {
  const { t } = useTranslation("review");
  const failure = useFailure();
  const create = useCreateThread(props.projectId);
  const visible = props.showResolved
    ? props.threads
    : props.threads.filter(
        (x) => x.status === "open" || x.id === props.activeId,
      );

  return (
    <aside
      aria-label={t("title")}
      data-testid="review-panel"
      className="flex flex-col"
      style={{
        width: 320,
        flexShrink: 0,
        minHeight: 0,
        borderLeft: "1px solid var(--border)",
        background: "var(--bg-0)",
      }}
    >
      <header
        className="flex items-center"
        style={{
          gap: 8,
          padding: "8px 10px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <MessageSquare size={13} />
        <strong style={{ fontSize: 12.5, flex: 1 }}>{t("title")}</strong>
        <button
          type="button"
          className="btn xs ghost"
          aria-pressed={props.showResolved}
          data-testid="review-filter"
          onClick={props.onToggleResolved}
        >
          {props.showResolved ? t("all") : t("open")}
        </button>
        <button
          type="button"
          className="icon-btn sm"
          aria-label={t("close")}
          onClick={props.onClose}
        >
          <X size={13} />
        </button>
      </header>
      <div
        className="flex flex-col"
        style={{ gap: 10, padding: 10, overflowY: "auto", flex: 1 }}
      >
        {props.pending && (
          <section
            data-testid="review-new-thread"
            style={{
              padding: 10,
              border: "1px solid var(--accent)",
              borderRadius: "var(--r-2)",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <strong style={{ fontSize: 12 }}>{t("newThread")}</strong>
            <span
              className="mono dim"
              style={{
                fontSize: 11.5,
                borderLeft: "3px solid var(--c-warn)",
                paddingLeft: 6,
              }}
            >
              {props.pending.anchor.quote.replace(/\s+/g, " ").slice(0, 160)}
            </span>
            <CommentComposer
              projectId={props.projectId}
              placeholder={t("placeholder")}
              submitLabel={t("send")}
              busy={create.isPending}
              error={create.isError ? failure(create.error) : null}
              autoFocus
              onSubmit={(body, mentions) => {
                const anchor = props.pending?.anchor;
                if (!anchor) return;
                create.mutate(
                  { path: props.path, anchor, body, mentions },
                  {
                    onSuccess: (thread) => {
                      props.onPendingDone();
                      props.onActivate(thread.id);
                    },
                  },
                );
              }}
              onCancel={props.onPendingDone}
            />
          </section>
        )}
        {visible.length === 0 && !props.pending && (
          <p
            className="dim"
            style={{ margin: 0, fontSize: 12.5 }}
            data-testid="review-empty"
          >
            {props.threads.length === 0 ? t("empty") : t("emptyOpen")}
          </p>
        )}
        {!props.canComment && (
          <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
            {t("readOnlyHint")}
          </p>
        )}
        {visible.map((thread) => (
          <ThreadCard
            key={thread.id}
            projectId={props.projectId}
            thread={thread}
            state={props.resolved.get(thread.id)?.state}
            active={props.activeId === thread.id}
            canComment={props.canComment}
            canModerate={props.canModerate}
            isOwner={props.isOwner}
            currentUserId={props.currentUserId}
            onActivate={() => {
              props.onActivate(thread.id);
            }}
          />
        ))}
      </div>
    </aside>
  );
};
