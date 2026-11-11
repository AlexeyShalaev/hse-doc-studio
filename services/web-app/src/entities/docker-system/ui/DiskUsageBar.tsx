import { formatBytes } from "@shared/lib";
import type { DiskSegment } from "../lib/diskSegments";

/**
 * Stacked bar of used disk space by category: segment widths are proportional
 * to bytes, every non-empty segment stays visible (min width), hover shows the
 * size.
 */
export const DiskUsageBar = ({
  segments,
}: {
  segments: readonly DiskSegment[];
}) => (
  <div
    data-testid="disk-usage-bar"
    className="flex items-center"
    style={{
      height: "1.375rem",
      borderRadius: "var(--r-2)",
      overflow: "hidden",
      background: "var(--bg-2)",
      gap: "0.125rem",
      padding: "0.125rem",
    }}
  >
    {segments.map((s) => (
      <div
        key={s.key}
        title={formatBytes(s.bytes)}
        style={{
          flex: `${s.bytes.toFixed(0)} 0 0`,
          height: "100%",
          borderRadius: "0.125rem",
          background: s.color,
          minWidth: "0.1875rem",
        }}
      />
    ))}
  </div>
);
