import type { GitCommitBrief } from "@entities/git-sync";
import { formatPastTime, initialsOf } from "@shared/lib";
import { sectionTitleStyle } from "../model/commitUi";

// Короткий список версий для панели и страницы истории: кто, что и когда.
// Версии коллег можно выбирать, чтобы посмотреть, что в них изменилось.

const CommitBody = ({
  commit,
  now,
}: {
  commit: GitCommitBrief;
  now: number;
}) => (
  <>
    <span
      aria-hidden="true"
      style={{
        width: 24,
        height: 24,
        borderRadius: "50%",
        flexShrink: 0,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 9.5,
        fontWeight: 700,
        background: "var(--accent-soft)",
        color: "var(--accent)",
        border: "1px solid var(--accent-line)",
      }}
    >
      {initialsOf(commit.author)}
    </span>
    <span style={{ minWidth: 0, flex: 1, textAlign: "left" }}>
      <span
        className="truncate"
        style={{ display: "block", fontSize: 12, color: "var(--fg-0)" }}
        title={commit.message}
      >
        {commit.message}
      </span>
      <span
        className="truncate"
        style={{ display: "block", fontSize: 11, color: "var(--fg-2)" }}
      >
        {commit.author}
        {" · "}
        {formatPastTime(commit.created_at, now)}
      </span>
    </span>
  </>
);

export const CommitRow = ({
  commit,
  now,
  selected,
  onSelect,
}: {
  commit: GitCommitBrief;
  now: number;
  /** Задано вместе с onSelect: строка становится кнопкой выбора. */
  selected?: boolean;
  onSelect?: (commitId: string) => void;
}) => {
  if (!onSelect) {
    return (
      <li
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "5px 0",
          minWidth: 0,
        }}
      >
        <CommitBody commit={commit} now={now} />
      </li>
    );
  }
  return (
    <li style={{ minWidth: 0 }}>
      <button
        type="button"
        className="sync-commit-btn"
        aria-pressed={selected === true}
        onClick={() => {
          onSelect(commit.id);
        }}
      >
        <CommitBody commit={commit} now={now} />
      </button>
    </li>
  );
};

export const CommitSection = ({
  title,
  total,
  commits,
  now,
  moreLabel,
  selectedId,
  onSelect,
  footer,
}: {
  title: string;
  total: number;
  commits: GitCommitBrief[];
  now: number;
  moreLabel: (count: number) => string;
  selectedId?: string | null;
  onSelect?: (commitId: string) => void;
  footer?: React.ReactNode;
}) => {
  if (commits.length === 0) return null;
  return (
    <section aria-label={title} style={{ minWidth: 0 }}>
      <div
        className="flex items-center"
        style={{ gap: 6, marginBottom: 2, justifyContent: "space-between" }}
      >
        <span style={sectionTitleStyle}>{title}</span>
        <span className="chip subtle tnum">{total}</span>
      </div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {commits.map((commit) => (
          <CommitRow
            key={commit.id}
            commit={commit}
            now={now}
            selected={selectedId === commit.id}
            {...(onSelect ? { onSelect } : {})}
          />
        ))}
      </ul>
      {total > commits.length && (
        <div className="dim" style={{ fontSize: 11, paddingTop: 2 }}>
          {moreLabel(total - commits.length)}
        </div>
      )}
      {footer}
    </section>
  );
};
