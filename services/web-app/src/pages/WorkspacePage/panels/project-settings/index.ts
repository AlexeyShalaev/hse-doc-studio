export { AuthorsSection } from "./AuthorsSection";
export type { AuthorsSectionProps } from "./AuthorsSection";
export { ConfidentialitySection } from "./ConfidentialitySection";
export type { ConfidentialitySectionProps } from "./ConfidentialitySection";
export { DangerZoneSection } from "./DangerZoneSection";
export type { DangerZoneSectionProps } from "./DangerZoneSection";
export { DocFormatsSection } from "./DocFormatsSection";
export type { DocFormatsSectionProps } from "./DocFormatsSection";
export { FontsSection } from "./FontsSection";
export type { FontsSectionProps } from "./FontsSection";
export { GeneralSection } from "./GeneralSection";
export type { GeneralSectionProps } from "./GeneralSection";
export { MetaSection } from "./MetaSection";
export type { MetaSectionProps } from "./MetaSection";
export { SharedDocsSection } from "./SharedDocsSection";
export type { SharedDocsSectionProps } from "./SharedDocsSection";
export { SupervisorSection } from "./SupervisorSection";
export type { SupervisorSectionProps } from "./SupervisorSection";

export {
  buildMetaBlocks,
  buildMetaGroupCards,
  collectManagedTeamAuthors,
  collectMetaFields,
  collectVariantRows,
  filterMetaFieldsBySection,
  groupMetaFields,
  groupVariantRows,
  metaGroupSection,
  shouldShowMetaGroupHeadings,
  SHARED_META_BLOCK_KEY,
  UNGROUPED_META_GROUP_ID,
} from "./sectionData";
export type {
  DocumentDefinition,
  DocumentVariant,
  MetaBlock,
  MetaBlockAuthor,
  MetaFieldEntry,
  MetaFieldGroup,
  MetaGroupCard,
  MetaGroupDef,
  MetaGroupSection,
  ProjectDocument,
  VariantGroup,
  VariantRow,
  VersionDetail,
} from "./sectionData";

export {
  DEFAULT_PROJECT_SETTINGS_SECTION,
  PROJECT_SETTINGS_SECTIONS,
  visibleProjectSettingsSections,
} from "./sectionRegistry";
export type {
  ProjectSettingsSectionContext,
  ProjectSettingsSectionDef,
  ProjectSettingsSectionId,
} from "./sectionRegistry";

export type { AuthorEntry, Person, PersonRole, Project } from "./types";

export {
  PROJECT_SETTINGS_GROUPS,
  DEFAULT_PROJECT_SETTINGS_GROUP,
  visibleProjectSettingsGroups,
  groupSections,
  resolveProjectSettingsGroup,
} from "./sectionRegistry";
export type {
  ProjectSettingsGroupId,
  ProjectSettingsGroupDef,
} from "./sectionRegistry";
