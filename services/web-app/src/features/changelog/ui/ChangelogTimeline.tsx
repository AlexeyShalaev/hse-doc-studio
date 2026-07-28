import { useTranslation } from "react-i18next";
import { useChangelog } from "@entities/changelog";
import { localeTag } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { clsx } from "clsx";
import type { ChangeLogEntryResponse, ChangeLogKind } from "@shared/api/types";

type ChangelogTimelineProps = {
  projectId: string;
  docId?: string;
};

const kindConfig: Record<
  ChangeLogKind,
  { icon: string; labelKey: string; sevClass: string }
> = {
  compile_ok: { icon: "✓", labelKey: "kind.compileOk", sevClass: "ok" },
  compile_fail: { icon: "✕", labelKey: "kind.compileFail", sevClass: "err" },
  manual_note: { icon: "✎", labelKey: "kind.manualNote", sevClass: "info" },
  pack_submission: {
    icon: "📦",
    labelKey: "kind.packSubmission",
    sevClass: "info",
  },
  sign: { icon: "✍", labelKey: "kind.sign", sevClass: "ok" },
  edit: { icon: "✏", labelKey: "kind.edit", sevClass: "" },
};

// Map the i18next interface language to a BCP-47 locale for date formatting.
const dateLocale = (): string => localeTag();

const formatDate = (isoString: string) => {
  const d = new Date(isoString);
  return d.toLocaleString(dateLocale(), {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

type EntryItemProps = {
  entry: ChangeLogEntryResponse;
};

const EntryItem = ({ entry }: EntryItemProps) => {
  const { t } = useTranslation("changelog");
  const cfg = kindConfig[entry.kind];
  const kindLabel = t(cfg.labelKey);

  const iconClass = clsx(
    "flex-shrink-0 w-7 h-7 rounded-pill border flex items-center justify-center text-xs font-bold",
    cfg.sevClass === "ok" && "text-c-ok bg-c-ok-soft border-c-ok/30",
    cfg.sevClass === "err" && "text-c-err bg-c-err-soft border-c-err/30",
    cfg.sevClass === "info" && "text-c-info bg-c-info-soft border-c-info/30",
    !cfg.sevClass && "text-fg-2 bg-bg-2 border-border",
  );

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={iconClass} title={kindLabel} aria-label={kindLabel}>
          {cfg.icon}
        </div>
        <div className="flex-1 w-px bg-border mt-1" />
      </div>
      <div className="flex-1 min-w-0 pb-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <div className="text-sm font-medium text-fg-0">{entry.summary}</div>
            {entry.note && (
              <div className="mt-1 text-xs text-fg-2 bg-bg-1 border border-border rounded-r-1 px-2 py-1 italic">
                {entry.note}
              </div>
            )}
          </div>
          <div className="flex-shrink-0 text-2xs text-fg-3 font-mono">
            {formatDate(entry.at)}
          </div>
        </div>
        {entry.doc_id && (
          <span className="mt-1 inline-block chip subtle">{entry.doc_id}</span>
        )}
      </div>
    </div>
  );
};

export const ChangelogTimeline = ({
  projectId,
  docId,
}: ChangelogTimelineProps) => {
  const { t } = useTranslation("changelog");
  const { data: entries, isLoading } = useChangelog(projectId, docId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Spinner />
      </div>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-fg-2 gap-2">
        <div className="text-2xl">📋</div>
        <div className="text-sm">{t("timeline.empty")}</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col p-4">
      {entries.map((entry) => (
        <EntryItem key={entry.id} entry={entry} />
      ))}
    </div>
  );
};
