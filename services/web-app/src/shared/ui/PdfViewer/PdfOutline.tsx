import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";

export type OutlineEntry = {
  title: string;
  pageNum: number | null;
  items: OutlineEntry[];
};

type PdfOutlineProps = {
  entries: OutlineEntry[];
  onJump: (pageNum: number) => void;
  depth?: number;
};

export const PdfOutline = ({ entries, onJump, depth = 0 }: PdfOutlineProps) => {
  return (
    <>
      {entries.map((entry, i) => (
        <OutlineRow
          key={`${String(depth)}-${String(i)}-${entry.title}`}
          entry={entry}
          onJump={onJump}
          depth={depth}
        />
      ))}
    </>
  );
};

const OutlineRow = ({
  entry,
  onJump,
  depth,
}: {
  entry: OutlineEntry;
  onJump: (pageNum: number) => void;
  depth: number;
}) => {
  const { t } = useTranslation("pdfViewer");
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = entry.items.length > 0;

  return (
    <>
      <div
        className="flex items-center"
        style={{ paddingLeft: 6 + depth * 12, gap: "0.125rem" }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="icon-btn xs"
            aria-label={open ? t("outline.collapse") : t("outline.expand")}
            onClick={() => {
              setOpen((v) => !v);
            }}
            style={{ flexShrink: 0 }}
          >
            {open ? (
              <ChevronDown size="0.75rem" />
            ) : (
              <ChevronRight size="0.75rem" />
            )}
          </button>
        ) : (
          <span style={{ width: "1.125rem", flexShrink: 0 }} />
        )}
        <button
          type="button"
          className="row-btn"
          style={{
            flex: 1,
            minWidth: 0,
            textAlign: "left",
            opacity: entry.pageNum == null ? 0.5 : 1,
            padding: "0.1875rem 0.25rem",
          }}
          disabled={entry.pageNum == null}
          onClick={() => {
            if (entry.pageNum != null) onJump(entry.pageNum);
          }}
          title={entry.title}
        >
          <span className="truncate" style={{ fontSize: "0.75rem" }}>
            {entry.title}
          </span>
        </button>
      </div>
      {open && hasChildren && (
        <PdfOutline entries={entry.items} onJump={onJump} depth={depth + 1} />
      )}
    </>
  );
};
