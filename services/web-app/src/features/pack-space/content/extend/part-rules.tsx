import type { ContentPartProps } from "../contract";
import { RuleFiles } from "../parts/RuleFiles";
import { VersionPart } from "../parts/VersionPart";

// S8d: раздел «Правила проверки»: что включено в версии и файлы с правилами, у которых своя форма
// (docs/design/pack-studio-ux.md, 12.10).
const RulesPart = (props: ContentPartProps) => (
  <VersionPart {...props}>
    <RuleFiles versionDir={props.versionDir} workspaceId={props.workspaceId} />
  </VersionPart>
);

export default RulesPart;
