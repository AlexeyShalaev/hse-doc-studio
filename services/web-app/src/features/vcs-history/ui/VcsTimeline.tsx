import type React from "react";
import { useTranslation } from "react-i18next";
import {
  Bookmark,
  CloudCheck,
  CloudDownload,
  CloudUpload,
  FileCog,
  GitCommitHorizontal,
  GitMerge,
  Hammer,
  type LucideIcon,
  Pencil,
  RotateCcw,
  Sparkles,
  Undo2,
} from "lucide-react";
import { clsx } from "clsx";
import { i18n, initialsOf, localeTag } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import type { VcsCommit } from "@entities/vcs";
import { isIncomingOnly, isOwnCommit } from "./vcsHistoryFilters.model";

// BCP-47 locale for date formatting, derived from the interface language.
const dateLocale = (): string => localeTag();

// Human-facing timeline of saved states — no git vocabulary (no commits, refs,
// branches). "Named" versions (the user pressed "Save version") are starred and
// prominent; "auto" rows are background saves shown subtly. The "auto" variant
// can group rows by day (sticky headers) and scroll internally so a long history
// doesn't stretch the whole page. With a connected repository each row also
// carries a sync marker (already pushed / waiting / received from a teammate)
// and teammates' versions get an initials avatar.

const AUTO_ICON: Record<string, LucideIcon> = {
  init: Sparkles,
  edit: Pencil,
  compile: Hammer,
  restore: Undo2,
  template_update: FileCog,
  sync: GitMerge,
};

const autoIcon = (kind: string): LucideIcon =>
  AUTO_ICON[kind] ?? GitCommitHorizontal;

const formatTime = (iso: string): string =>
  new Date(iso).toLocaleString(dateLocale(), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

const dayKey = (iso: string): string => {
  const d = new Date(iso);
  return `${String(d.getFullYear())}-${String(d.getMonth())}-${String(d.getDate())}`;
};

const startOfDay = (d: Date): Date =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate());

const dayLabel = (iso: string): string => {
  const d = new Date(iso);
  const today = startOfDay(new Date());
  const that = startOfDay(d);
  const diffDays = Math.round((today.getTime() - that.getTime()) / 86_400_000);
  if (diffDays === 0) return i18n.t("vcsHistory:timeline.today");
  if (diffDays === 1) return i18n.t("vcsHistory:timeline.yesterday");
  const sameYear = d.getFullYear() === today.getFullYear();
  return d.toLocaleDateString(dateLocale(), {
    day: "numeric",
    month: "long",
    ...(sameYear ? {} : { year: "numeric" }),
  });
};

const SYNC_MARK: Record<
  string,
  { icon: LucideIcon; color: string; key: string }
> = {
  pushed: { icon: CloudCheck, color: "var(--fg-3)", key: "pushed" },
  unpushed: { icon: CloudUpload, color: "var(--c-warn)", key: "unpushed" },
  incoming: { icon: CloudDownload, color: "var(--c-info)", key: "incoming" },
};

export type VcsTimelineProps = {
  commits: VcsCommit[];
  selectedId: string | null;
  headId: string | null;
  variant: "named" | "auto";
  onSelect: (commitId: string) => void;
  onRestore: (commit: VcsCommit) => void;
  /** Insert sticky per-day headers (commits are assumed sorted newest-first). */
  groupByDate?: boolean;
  /** Cap the list height and scroll inside instead of growing the page. */
  maxHeight?: number;
  /** E-mail of the current author: versions by anyone else get an avatar. */
  meEmail?: string | null;
  /** More rows exist on the server: shows the "Show more" footer. */
  hasMore?: boolean;
  isLoadingMore?: boolean;
  onLoadMore?: () => void;
};

export const VcsTimeline = ({
  commits,
  selectedId,
  headId,
  variant,
  onSelect,
  onRestore,
  groupByDate = false,
  maxHeight,
  meEmail = null,
  hasMore = false,
  isLoadingMore = false,
  onLoadMore,
}: VcsTimelineProps) => {
  const { t } = useTranslation("vcsHistory");
  const named = variant === "named";
  const hasFooter = hasMore && onLoadMore !== undefined;

  const renderRow = (commit: VcsCommit, isLast: boolean): React.ReactNode => {
    const isActive = selectedId === commit.id;
    const isHead = headId === commit.id;
    const merge = commit.is_merge === true;
    const incomingOnly = isIncomingOnly(commit);
    const own = isOwnCommit(commit, meEmail);
    const Icon = named ? Bookmark : merge ? GitMerge : autoIcon(commit.kind);
    const mark = commit.sync ? SYNC_MARK[commit.sync] : undefined;
    const files =
      commit.stats && commit.stats.files > 0 ? commit.stats.files : 0;
    const markLabel = mark
      ? t(`timeline.sync.${mark.key}`, { author: commit.author })
      : "";

    const meta: string[] = [formatTime(commit.created_at)];
    if (merge) {
      meta.push(
        files > 0
          ? t("timeline.merge", { count: files })
          : t("timeline.mergePlain"),
      );
    } else if (files > 0) {
      meta.push(t("timeline.files", { count: files }));
    }
    if (!own) meta.push(commit.author);

    return (
      <div
        key={commit.id}
        className={clsx("flex items-center", isActive && "active")}
        data-sync={commit.sync ?? undefined}
        style={{
          padding: "10px 14px",
          gap: 12,
          borderBottom: isLast && !hasFooter ? 0 : "1px solid var(--border)",
          background: isActive ? "var(--accent-soft)" : undefined,
          cursor: "pointer",
        }}
        onClick={() => {
          onSelect(commit.id);
        }}
      >
        <Icon
          size={named ? 15 : 13}
          aria-hidden="true"
          style={{
            color: named ? "var(--accent)" : "var(--fg-3)",
            flexShrink: 0,
          }}
        />
        <div className="flex flex-col min-w-0" style={{ gap: 1, flex: 1 }}>
          <span
            className="truncate"
            style={{
              fontSize: named ? 13 : 12.5,
              fontWeight: named ? 600 : 400,
              color: "var(--fg-0)",
            }}
            title={commit.message}
          >
            {commit.message}
          </span>
          <span className="dim truncate" style={{ fontSize: 10.5 }}>
            {meta.join(" · ")}
          </span>
        </div>
        {!own && (
          <span
            role="img"
            aria-label={commit.author}
            title={commit.author}
            style={{
              width: 22,
              height: 22,
              borderRadius: "50%",
              flexShrink: 0,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 9,
              fontWeight: 700,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              border: "1px solid var(--accent-line)",
            }}
          >
            {initialsOf(commit.author)}
          </span>
        )}
        {mark && (
          <span
            role="img"
            aria-label={markLabel}
            title={markLabel}
            data-testid="sync-mark"
            style={{
              display: "inline-flex",
              color: mark.color,
              flexShrink: 0,
            }}
          >
            <mark.icon size={14} aria-hidden="true" />
          </span>
        )}
        {isHead ? (
          <span
            className="chip"
            style={{
              fontSize: 9.5,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              borderColor: "var(--accent-line)",
              flexShrink: 0,
            }}
          >
            {t("timeline.current")}
          </span>
        ) : (
          <button
            type="button"
            className="btn xs"
            disabled={incomingOnly}
            title={incomingOnly ? t("timeline.restoreIncoming") : undefined}
            onClick={(e) => {
              e.stopPropagation();
              onRestore(commit);
            }}
          >
            <RotateCcw size={11} aria-hidden="true" />
            {t("timeline.restore")}
          </button>
        )}
      </div>
    );
  };

  let body: React.ReactNode;
  if (groupByDate) {
    const dayCounts = new Map<string, number>();
    commits.forEach((c) => {
      const k = dayKey(c.created_at);
      dayCounts.set(k, (dayCounts.get(k) ?? 0) + 1);
    });
    const rows: React.ReactNode[] = [];
    let lastDay = "";
    commits.forEach((commit, idx) => {
      const k = dayKey(commit.created_at);
      if (k !== lastDay) {
        lastDay = k;
        rows.push(
          <div key={`day-${k}`} className="vcs-day-header">
            <span>{dayLabel(commit.created_at)}</span>
            <span style={{ fontWeight: 400, color: "var(--fg-3)" }}>
              {String(dayCounts.get(k) ?? 0)}
            </span>
          </div>,
        );
      }
      rows.push(renderRow(commit, idx === commits.length - 1));
    });
    body = rows;
  } else {
    body = commits.map((commit, i) =>
      renderRow(commit, i === commits.length - 1),
    );
  }

  const footer = hasFooter ? (
    <div
      className="flex items-center justify-center"
      style={{ padding: "10px 14px" }}
    >
      <button
        type="button"
        className="btn xs"
        onClick={onLoadMore}
        disabled={isLoadingMore}
      >
        {isLoadingMore && <Spinner size="sm" />}
        {t("timeline.showMore")}
      </button>
    </div>
  ) : null;

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {maxHeight != null ? (
        <div style={{ maxHeight, overflowY: "auto" }}>
          {body}
          {footer}
        </div>
      ) : (
        <>
          {body}
          {footer}
        </>
      )}
    </div>
  );
};
