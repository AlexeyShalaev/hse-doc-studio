import type { ReactNode } from "react";
import type { DiskSegment } from "../lib/diskSegments";
import { DiskUsageBar } from "./DiskUsageBar";
import { DiskUsageLegend } from "./DiskUsageLegend";

/**
 * The «Диск» overview block: a header row (total on the left, `aside` such as
 * «можно освободить» and a refresh button on the right), then the bar and its
 * legend.
 */
export const DiskUsageOverview = ({
  segments,
  title,
  aside,
}: {
  segments: readonly DiskSegment[];
  title: ReactNode;
  aside?: ReactNode;
}) => (
  <div className="flex flex-col" style={{ gap: "0.625rem" }}>
    <div
      className="flex items-center justify-between"
      style={{ gap: "0.5rem" }}
    >
      <span style={{ fontSize: "0.8125rem", fontWeight: 600 }}>{title}</span>
      {aside != null && (
        <span className="flex items-center" style={{ gap: "0.5rem" }}>
          {aside}
        </span>
      )}
    </div>
    <DiskUsageBar segments={segments} />
    <DiskUsageLegend segments={segments} />
  </div>
);
