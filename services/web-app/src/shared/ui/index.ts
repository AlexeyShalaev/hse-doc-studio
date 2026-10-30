export { Button } from "./Button";
export type { ButtonProps } from "./Button";

export { Badge } from "./Badge";
export type { BadgeProps } from "./Badge";

export { Spinner } from "./Spinner";
export type { SpinnerProps } from "./Spinner";

export { Tooltip, TooltipProvider } from "./Tooltip";
export type { TooltipProps } from "./Tooltip";

export { UiVariantContext, useUiVariant } from "./UiVariant";
export type { UiVariant } from "./UiVariant";

export { Modal } from "./Modal";
export type { ModalProps } from "./Modal";

export { Select } from "./Select";
export type { SelectProps, SelectOption } from "./Select";

export { Combobox } from "./Combobox";
export type { ComboboxProps, ComboboxOption } from "./Combobox";

export { Input } from "./Input";
export type { InputProps } from "./Input";

export { Textarea } from "./Textarea";
export type { TextareaProps } from "./Textarea";

export { StatusBadge } from "./StatusBadge";
export type { StatusBadgeProps } from "./StatusBadge";

export { ResizeHandle } from "./ResizeHandle";
export type { ResizeHandleProps } from "./ResizeHandle";

export { ReadinessRing } from "./ReadinessRing";
export type { ReadinessRingProps } from "./ReadinessRing";

export {
  CodeEditor,
  addColumn,
  addEntry,
  addRow,
  escapeLatex,
  hasEmptyKey,
  htmlToLatex,
  latexToHtml,
  moveColumn,
  moveEntry,
  parseEditableBibliography,
  parseEditableTable,
  removeColumn,
  removeEntry,
  removeRow,
  sanitizeKey,
  serializeEditableBibliography,
  serializeEditableTable,
  setCellValue,
  setColumnAlign,
  setColumnLabel,
  setEntryKey,
  setEntryValue,
} from "./CodeEditor";
export type {
  BibEntry,
  BibliographyDraft,
  BibScaffold,
  ColumnAlign,
  DraftCell,
  DraftColumn,
  DraftTable,
  ParsedBibliography,
  ParsedEditableTable,
  TableScaffold,
} from "./CodeEditor";
export type {
  CodeEditorController,
  CodeEditorProps,
  DiagnosticClickInfo,
  EditorCommandId,
  EditorDiagnostic,
  EditorFormatState,
  EditorLanguage,
  EditorQuickFix,
  EditorStats,
  OutlineItem,
  OutlineState,
  RevealRequest,
  VisualEmbeddedInputKind,
  VisualEditorOptions,
  VisualHeadingAlignment,
} from "./CodeEditor";

export { PdfViewer, PdfDiffView } from "./PdfViewer";
export type {
  PdfViewerProps,
  PdfStamp,
  PageMargins,
  PdfDiffViewProps,
  DiffBaseOption,
} from "./PdfViewer";

export { Toaster } from "./Toaster";

export {
  Popover,
  PopoverAnchor,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
} from "./Popover";
export type { PopoverContentProps } from "./Popover";

export { CopyField } from "./CopyField";
export type { CopyFieldProps } from "./CopyField";

export { LinkDelivery } from "./LinkDelivery";
export type { LinkDeliveryProps } from "./LinkDelivery";

export { ProgressBar } from "./ProgressBar";
export type { ProgressBarProps } from "./ProgressBar";
export { FileDropZone } from "./FileDropZone";
export type { FileDropZoneHandle, FileDropZoneProps } from "./FileDropZone";

export { Facts, ResultFrame } from "./ResultFrame";
export type { FrameTone } from "./ResultFrame";

export { Stepper } from "./Stepper";
export type { StepperProps, StepperStep, StepState } from "./Stepper";

export { DiffPatch, changeMeta, countChanges, parsePatch } from "./DiffPatch";
export type {
  DiffChangeMeta,
  PatchLineKind,
  DiffPatchFile,
  DiffPatchProps,
  DiffStat,
  ParsedDiffLine,
  ParsedHunk,
} from "./DiffPatch";

export {
  ActionTag,
  CountBadges,
  FileList,
  FileRowShell,
  Notice,
  ViewTabs,
  toneColor,
  toneSoft,
} from "./ConflictKit";
export type {
  ActionTagProps,
  ConflictTone,
  CountBadge,
  FileListProps,
  FileRowShellProps,
  NoticeProps,
  NoticeTone,
  ViewTab,
  ViewTabsProps,
} from "./ConflictKit";

export { DataTable } from "./DataTable";
export type { DataTableProps, DataTablePagination } from "./DataTable";

export {
  ActiveFilters,
  DateRangeFilter,
  FilterBar,
  FilterMenu,
  isoDay,
  SortSelect,
  SortMenu,
  useDateRangeLabel,
} from "./FilterBar";
export type {
  ActiveFilter,
  ActiveFiltersProps,
  DateRange,
  DateRangeFilterProps,
  FilterBarProps,
  FilterGroup,
  FilterMenuProps,
  FilterOption,
  SortOption,
  SortSelectProps,
  SortMenuOption,
  SortMenuProps,
  SortMenuValue,
} from "./FilterBar";

// Серверные списки: листание, поиск и пикеры (галерея «Примитивы админки»).
export { Pagination } from "./Pagination";
export type {
  CursorPaginationProps,
  OffsetPaginationProps,
  PaginationProps,
} from "./Pagination";
export { SearchInput } from "./SearchInput";
export type { SearchInputProps } from "./SearchInput";
export {
  Picker,
  PickerFilter,
  PickerItemIcon,
  PickerPanel,
  usePickedItem,
} from "./Picker";
export type {
  PickerFilterProps,
  PickerPanelProps,
  PickerProps,
  PickerSource,
} from "./Picker";

export { ConfirmByName } from "./ConfirmByName";
export type { ConfirmByNameProps } from "./ConfirmByName";

export { SecretOnce } from "./SecretOnce";
export type { SecretOnceProps } from "./SecretOnce";

export { StatusDot } from "./StatusDot";
export type { StatusDotProps, StatusDotStatus } from "./StatusDot";

// Набор блоков страниц админки (галерея: /dev/server-screens → «Примитивы админки»).
export { AdminPage, PageContainer, PageHeader, PageTabs } from "./AdminPage";
export type {
  AdminPageProps,
  PageContainerProps,
  PageHeaderProps,
  PageTab,
  PageTabsProps,
  PageWidth,
} from "./AdminPage";

export { ListRow, Section, SectionList, SettingRow } from "./Section";
export type {
  ListRowProps,
  ListRowTone,
  SectionProps,
  SettingRowProps,
} from "./Section";

export { StickySaveBar } from "./StickySaveBar";
export type { StickySaveBarProps } from "./StickySaveBar";

export { KpiGrid, KpiTile, Meter, Sparkline } from "./KpiTile";
export type { KpiTileProps, KpiTone } from "./KpiTile";

export { EmptyState, ErrorState, NoResults } from "./EmptyState";
export type {
  EmptyStateProps,
  ErrorStateProps,
  NoResultsProps,
} from "./EmptyState";

export { TableSkeleton } from "./TableSkeleton";
export type { TableSkeletonProps } from "./TableSkeleton";

export { Avatar, PersonCell } from "./PersonCell";
export type { AvatarProps, PersonCellProps } from "./PersonCell";

export { ActionMenu } from "./ActionMenu";
export type { ActionMenuItem, ActionMenuProps } from "./ActionMenu";
