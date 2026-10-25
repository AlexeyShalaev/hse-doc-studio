export { templateUpdateApi } from "./api/templateUpdateApi";
export type {
  ApplyTemplateUpdateParams,
  ConflictResolution,
  RevertTemplateUpdateParams,
  TemplateDiffParams,
  TemplateDiffView,
} from "./api/templateUpdateApi";
export {
  templateUpdateKeys,
  useTemplateUpdateStatus,
  useTemplateUpdatePlan,
  useTemplateFileDiff,
  useCompareWithTemplate,
  useApplyTemplateUpdate,
  useRevertTemplateUpdate,
  useSetTemplateTracking,
} from "./api/templateUpdateQueries";
export type {
  AvailableUpdate,
  ApplyTemplateUpdateResult,
  CompareWithTemplate,
  RevertTemplateUpdateResult,
  TemplateDiff,
  TemplateFileOp,
  TemplateFileState,
  TemplateUpdatePlan,
  TemplateUpdateRecord,
  TemplateUpdateStatus,
  TemplateVersionInfo,
  UpdateWarning,
} from "./api/templateUpdateSchemas";
