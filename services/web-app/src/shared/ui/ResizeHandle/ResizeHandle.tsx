import type { PointerEvent } from "react";

// How much one arrow-key press changes the pane width (px).
const RESIZE_STEP = 16;

export type ResizeHandleProps = {
  active: boolean;
  label: string;
  onDoubleClick: () => void;
  onKeyNudge: (delta: number) => void;
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void;
};

// Vertical drag separator for a resizable docked pane. Pairs with the
// usePaneResize hook: wire active/onDoubleClick/onKeyNudge/onPointerDown to it.
export const ResizeHandle = ({
  active,
  label,
  onDoubleClick,
  onKeyNudge,
  onPointerDown,
}: ResizeHandleProps) => (
  <div
    role="separator"
    aria-label={label}
    aria-orientation="vertical"
    className="split-resize-handle"
    data-resizing={active ? "true" : undefined}
    tabIndex={0}
    title={label}
    onDoubleClick={onDoubleClick}
    onKeyDown={(event) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        onKeyNudge(-RESIZE_STEP);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        onKeyNudge(RESIZE_STEP);
      }
    }}
    onPointerDown={onPointerDown}
  />
);
