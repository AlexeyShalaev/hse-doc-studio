import type React from "react";
import { useTranslation } from "react-i18next";
import {
  Bookmark,
  GitCommitHorizontal,
  Hammer,
  type LucideIcon,
  Pencil,
  RotateCcw,
  Sparkles,
  Undo2,
} from "lucide-react";
import { clsx } from "clsx";
import { i18n, localeTag } from "@shared/lib";
import type { VcsCommit } from "@entities/vcs";

// BCP-47 locale for date formatting, derived from the interface language.
const dateLocale = (): string => localeTag();

// Human-facing timeline of saved states — no git vocabulary (no commits, refs,
// branches). "Named" versions (the user pressed "Save version") are starred and
// prominent; "auto" rows are background saves shown subtly. The "auto" variant
// can group rows by day (sticky headers) and scroll internally so a long history
// doesn't stretch the whole page.

const AUTO_ICON: Record<string, LucideIcon> = {
  init: Sparkles,
  edit: Pencil,
  compile: Hammer,
  restore: Undo2,
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
}: VcsTimelineProps) => {
  const { t } = useTranslation("vcsHistory");
  const named = variant === "named";

  const renderRow = (commit: VcsCommit, isLast: boolean): React.ReactNode => {
    const isActive = selectedId === commit.id;
    const isHead = headId === commit.id;
    const Icon = named ? Bookmark : autoIcon(commit.kind);
    return (
      <div
        key={commit.id}
        className={clsx("flex items-center", isActive && "active")}
        style={{
          padding: "10px 14px",
          gap: 12,
          borderBottom: isLast ? 0 : "1px solid var(--border)",
          background: isActive ? "var(--accent-soft)" : undefined,
          cursor: "pointer",
        }}
        onClick={() => {
          onSelect(commit.id);
        }}
      >
        <Icon
          size={named ? 15 : 13}
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
          <span className="dim" style={{ fontSize: 10.5 }}>
            {formatTime(commit.created_at)}
            {commit.stats && commit.stats.files > 0
              ? ` · ${t("timeline.files", { count: commit.stats.files })}`
              : ""}
          </span>
        </div>
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
            onClick={(e) => {
              e.stopPropagation();
              onRestore(commit);
            }}
          >
            <RotateCcw size={11} />
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

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {maxHeight != null ? (
        <div style={{ maxHeight, overflowY: "auto" }}>{body}</div>
      ) : (
        body
      )}
    </div>
  );
};
