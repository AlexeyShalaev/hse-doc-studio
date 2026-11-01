import {
  Hourglass,
  Laptop,
  Server,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CompilePlacement } from "@entities/runner";
import {
  placementView,
  type PlacementPerspective,
  type PlacementTone,
  type PlacementView,
} from "../lib/placementView";

const ICON: Record<PlacementView["kind"], LucideIcon> = {
  waiting: Hourglass,
  personal: Laptop,
  shared: Server,
  fallback: TriangleAlert,
};

const COLOR: Record<PlacementTone, string> = {
  ok: "var(--c-ok)",
  info: "var(--c-info)",
  warn: "var(--c-warn)",
  neutral: "var(--fg-2)",
};

export type BuildPlacementChipProps = {
  placement: CompilePlacement;
  /** Свой проект или чужой (соавтор): от этого зависит «ваш раннер» или «раннер владельца». */
  perspective?: PlacementPerspective;
};

/** Где идёт сборка: личный раннер, ожидание его, общий раннер или фолбэк с причиной. */
export const BuildPlacementChip = ({
  placement,
  perspective = "me",
}: BuildPlacementChipProps) => {
  const { t } = useTranslation("documents");
  const view = placementView(placement, perspective);
  const Icon = ICON[view.kind];
  const text = t(`compile.placement.${view.key}`, view.params);
  return (
    <span
      className="chip sans"
      role="status"
      title={text}
      data-testid="build-placement"
      data-state={placement.state}
      data-fallback={placement.fallback ?? undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        maxWidth: "100%",
        fontSize: 11,
        color: COLOR[view.tone],
        borderColor:
          view.tone === "neutral"
            ? undefined
            : `color-mix(in oklch, ${COLOR[view.tone]} 40%, var(--border))`,
      }}
    >
      <Icon size={11} aria-hidden="true" style={{ flexShrink: 0 }} />
      <span className="truncate" style={{ color: "var(--fg-1)" }}>
        {text}
      </span>
    </span>
  );
};
