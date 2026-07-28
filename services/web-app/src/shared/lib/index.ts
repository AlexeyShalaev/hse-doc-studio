export { createSSEStream } from "./sse";
export type { SSEEvent } from "./sse";

export { toPosixPath } from "./path";

export { formatBytes } from "./formatBytes";

export { diffHunks, diffLines } from "./lineDiff";
export type { DiffLine, DiffLineKind } from "./lineDiff";

export { EDITABLE_TEXT_EXTENSIONS, isEditableTextPath } from "./fileTypes";

export { useThemeStore, useApplyTheme } from "./theme";
export type { Theme, Density } from "./theme";

export {
  VISUAL_ZOOM_MAX,
  VISUAL_ZOOM_MIN,
  VISUAL_ZOOM_STEP,
  useEditorPrefsStore,
} from "./editorPrefs";
export type { SourceEditorMode } from "./editorPrefs";

export {
  useWorkspaceStore,
  getLastDoc,
  setLastDoc,
  forgetLastDoc,
} from "./workspace";
export type { WorkbenchActivity } from "./workspace";

export {
  RECENT_PROJECTS_LIMIT,
  useRecentProjectsStore,
  useRecentProjectIds,
} from "./recent-projects";
export type { RecentProjectEntry } from "./recent-projects";

export {
  resolveSelectedAuthorSlug,
  useSubmissionAuthor,
  useSubmissionAuthorStore,
} from "./submission-author";
export type { SubmissionAuthorSelection } from "./submission-author";

export { useSyncTexStore } from "./synctex";
export type { PdfJump, SourceJump, SourceFind } from "./synctex";

export { usePaneResize } from "./resize";
export type { PaneResize, PaneResizeConfig } from "./resize";

export { useGlobalHotkeys } from "./hotkeys";
export type { GlobalHotkeyHandlers } from "./hotkeys";

export { useUIStore } from "./ui";

export { useToastStore, toast } from "./toast";
export type { Toast, ToastKind } from "./toast";

export { i18n, useApplyLanguage, pickLocalized, localeTag } from "./i18n";

export {
  academicYearEnd,
  resolveMetaAuto,
  metaFieldDefault,
  isMetaValueBlank,
  seedMetaDefaults,
  metaFieldVisibleForKind,
} from "./metaFields";
