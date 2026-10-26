import type { ReactNode } from "react";
import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import { type ConflictTone, toneColor, toneSoft } from "./conflictTone";

// Presentational pieces shared by the template-update preview and the git
// conflict screens. They know nothing about either domain: callers pass already
// translated text and a tone.

/** Small coloured status word in front of a file name ("conflict", "new"). */
export type ActionTagProps = {
  label: string;
  tone: ConflictTone;
  /** Reserve a column so the paths of neighbouring rows line up. */
  minWidth?: number;
};

export const ActionTag = ({ label, tone, minWidth = 74 }: ActionTagProps) => (
  <span
    style={{
      fontSize: 10.5,
      fontWeight: 600,
      color: toneColor(tone),
      minWidth,
    }}
  >
    {label}
  </span>
);

/** Selectable file row: tag + mono path + trailing slot, optional controls below. */
export type FileRowShellProps = {
  path: string;
  isSelected: boolean;
  onSelect: () => void;
  tag?: ReactNode;
  /** Right-aligned content on the main line (icons, counters). */
  trailing?: ReactNode;
  /** Controls under the path (e.g. a resolution select), aligned with the path. */
  children?: ReactNode;
  /** Left offset of `children`; defaults to the width of the tag column. */
  childrenIndent?: number;
};

export const FileRowShell = ({
  path,
  isSelected,
  onSelect,
  tag,
  trailing,
  children,
  childrenIndent = 82,
}: FileRowShellProps) => (
  <div
    style={{
      padding: "6px 8px",
      borderRadius: "var(--r-2)",
      background: isSelected ? "var(--accent-soft)" : undefined,
    }}
  >
    <button
      type="button"
      className="flex items-center"
      onClick={onSelect}
      data-file-row=""
      aria-current={isSelected ? "true" : undefined}
      style={{
        gap: 8,
        width: "100%",
        background: "none",
        border: 0,
        padding: 0,
        cursor: "pointer",
        textAlign: "left",
      }}
    >
      {tag}
      <span
        className="mono truncate"
        style={{ fontSize: 11.5, flex: 1, color: "var(--fg-0)" }}
        title={path}
      >
        {path}
      </span>
      {trailing}
    </button>
    {children != null && (
      <div style={{ marginTop: 6, marginLeft: childrenIndent }}>{children}</div>
    )}
  </div>
);

/** Scrollable bordered column that holds `FileRowShell`s. */
export type FileListProps = {
  children: ReactNode;
  /** Height limit in px; "none" leaves scrolling to the parent. */
  maxHeight?: number | "none";
};

export const FileList = ({ children, maxHeight = 420 }: FileListProps) => (
  <div
    className="card"
    style={
      maxHeight === "none"
        ? { padding: 4 }
        : { overflow: "auto", maxHeight, padding: 4 }
    }
  >
    {children}
  </div>
);

/** Banner with an icon. `warn` is the default; `info` and `err` for the rest. */
export type NoticeTone = "warn" | "info" | "err";

export type NoticeProps = {
  text: ReactNode;
  tone?: NoticeTone;
  /** `alert` for errors the user must notice, `status` for passive info. */
  role?: "alert" | "status";
  /** Extra controls on the right (a "Retry" button). */
  action?: ReactNode;
};

const NOTICE_ICON = {
  warn: AlertTriangle,
  info: Info,
  err: OctagonAlert,
} as const;

export const Notice = ({ text, tone = "warn", role, action }: NoticeProps) => {
  const Icon = NOTICE_ICON[tone];
  return (
    <div
      role={role}
      className="flex items-start"
      style={{
        gap: 8,
        padding: "8px 10px",
        borderRadius: "var(--r-2)",
        background: toneSoft(tone),
        fontSize: 11.5,
        lineHeight: 1.5,
      }}
    >
      <Icon
        size={13}
        aria-hidden="true"
        style={{ color: toneColor(tone), flexShrink: 0, marginTop: 2 }}
      />
      <span style={{ flex: 1, minWidth: 0 }}>{text}</span>
      {action}
    </div>
  );
};

/** Row of "<count> · <label>" badges coloured by tone. */
export type CountBadge = {
  key: string;
  count: number;
  label: string;
  tone: ConflictTone;
};

export const CountBadges = ({ items }: { items: CountBadge[] }) => (
  <div className="flex" style={{ gap: 6, flexWrap: "wrap" }}>
    {items.map((item) => (
      <span
        key={item.key}
        className="badge"
        style={{ color: toneColor(item.tone), fontSize: 11 }}
      >
        {item.count} · {item.label}
      </span>
    ))}
  </div>
);

/** Compact tab strip that switches which side of a file is shown. */
export type ViewTab<V extends string> = { value: V; label: string };

export type ViewTabsProps<V extends string> = {
  views: ViewTab<V>[];
  value: V;
  onChange: (value: V) => void;
};

export const ViewTabs = <V extends string>({
  views,
  value,
  onChange,
}: ViewTabsProps<V>) => (
  <div className="flex" style={{ gap: 4 }}>
    {views.map((view) => (
      <button
        key={view.value}
        type="button"
        className={view.value === value ? "btn xs primary" : "btn xs"}
        onClick={() => {
          onChange(view.value);
        }}
      >
        {view.label}
      </button>
    ))}
  </div>
);
