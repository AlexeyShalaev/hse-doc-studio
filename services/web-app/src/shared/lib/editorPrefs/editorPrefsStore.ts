import { create } from "zustand";
import { persist } from "zustand/middleware";

/** Source-editor presentation: raw LaTeX vs Overleaf-style visual editing. */
export type SourceEditorMode = "code" | "visual";

export const VISUAL_ZOOM_MIN = 80;
export const VISUAL_ZOOM_MAX = 140;
export const VISUAL_ZOOM_STEP = 10;

const clampVisualZoom = (value: number): number =>
  Math.min(
    VISUAL_ZOOM_MAX,
    Math.max(
      VISUAL_ZOOM_MIN,
      Math.round(value / VISUAL_ZOOM_STEP) * VISUAL_ZOOM_STEP,
    ),
  );

type EditorPrefsState = {
  sourceMode: SourceEditorMode;
  /** Visual mode: show full-line comments dimmed instead of collapsing them. */
  showComments: boolean;
  /** Visual mode: Word-style headings navigation pane on the left. */
  showOutline: boolean;
  /** Visual mode: document-canvas zoom in percent. */
  visualZoom: number;
};

type EditorPrefsActions = {
  setSourceMode: (mode: SourceEditorMode) => void;
  toggleShowComments: () => void;
  toggleShowOutline: () => void;
  setVisualZoom: (zoom: number) => void;
  zoomVisualIn: () => void;
  zoomVisualOut: () => void;
  resetVisualZoom: () => void;
};

/**
 * Sticky editor preferences (global, like Overleaf's editor-mode setting).
 * Separate from the theme store: app chrome vs editor behavior.
 */
export const useEditorPrefsStore = create<
  EditorPrefsState & EditorPrefsActions
>()(
  persist(
    (set) => ({
      // Writing is the primary workflow. Existing users keep their persisted
      // preference, while a new workspace opens a safe, round-trip visual
      // surface and still exposes raw LaTeX one click away.
      sourceMode: "visual",
      showComments: false,
      showOutline: true,
      visualZoom: 100,
      setSourceMode: (sourceMode) => set({ sourceMode }),
      toggleShowComments: () =>
        set((state) => ({ showComments: !state.showComments })),
      toggleShowOutline: () =>
        set((state) => ({ showOutline: !state.showOutline })),
      setVisualZoom: (visualZoom) =>
        set({ visualZoom: clampVisualZoom(visualZoom) }),
      zoomVisualIn: () =>
        set((state) => ({
          visualZoom: clampVisualZoom(state.visualZoom + VISUAL_ZOOM_STEP),
        })),
      zoomVisualOut: () =>
        set((state) => ({
          visualZoom: clampVisualZoom(state.visualZoom - VISUAL_ZOOM_STEP),
        })),
      resetVisualZoom: () => set({ visualZoom: 100 }),
    }),
    {
      name: "hse-editor-prefs",
      partialize: (state) => ({
        sourceMode: state.sourceMode,
        showComments: state.showComments,
        showOutline: state.showOutline,
        visualZoom: state.visualZoom,
      }),
    },
  ),
);
