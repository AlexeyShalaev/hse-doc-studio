import { formatBytes } from "@shared/lib";
import type { DiskSegment } from "../lib/diskSegments";

/** Legend under {@link DiskUsageBar}: colour swatch, label and size. */
export const DiskUsageLegend = ({
  segments,
}: {
  segments: readonly DiskSegment[];
}) => (
  <div
    data-testid="disk-usage-legend"
    className="flex flex-wrap items-center"
    style={{ gap: "0.375rem 1rem", fontSize: "0.71875rem" }}
  >
    {segments.map((s) => (
      <div
        key={s.key}
        data-testid="disk-usage-legend-item"
        className="flex items-center"
        style={{ gap: "0.375rem" }}
      >
        <DiskCategorySwatch color={s.color} />
        <span className="dim">{s.label}</span>
        <span className="mono">{formatBytes(s.bytes)}</span>
      </div>
    ))}
  </div>
);

/** Small square in a category's colour (legend, image rows). */
export const DiskCategorySwatch = ({ color }: { color: string }) => (
  <span
    style={{
      width: "0.5rem",
      height: "0.5rem",
      borderRadius: "0.125rem",
      background: color,
      flexShrink: 0,
    }}
  />
);
