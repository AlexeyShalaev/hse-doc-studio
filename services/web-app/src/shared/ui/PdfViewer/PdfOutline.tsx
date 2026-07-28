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
        style={{ paddingLeft: 6 + depth * 12, gap: 2 }}
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
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        ) : (
          <span style={{ width: 18, flexShrink: 0 }} />
        )}
        <button
          type="button"
          className="row-btn"
          style={{
            flex: 1,
            minWidth: 0,
            textAlign: "left",
            opacity: entry.pageNum == null ? 0.5 : 1,
            padding: "3px 4px",
          }}
          disabled={entry.pageNum == null}
          onClick={() => {
            if (entry.pageNum != null) onJump(entry.pageNum);
          }}
          title={entry.title}
        >
          <span className="truncate" style={{ fontSize: 12 }}>
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
