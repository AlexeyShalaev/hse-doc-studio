import type { ContentPart, ContentPartProps } from "../contract";
import { useContentNav } from "../useContentNav";
import { LegacyFormPane } from "./LegacyFormPane";

// ВРЕМЕННО (S8d): раздел версии как раздел прежней формы версии. Прежняя форма открывается на
// разделе, где живёт указатель `at` (так она выбирает вкладку), поэтому каждому разделу навигации
// дан указатель на его верхний ключ манифеста. Полоса вкладок формы остаётся: в ней доступен
// «Документы» (состав документов версии), которому в новой навигации пока нет своего места.
// «Подписи и места» и «Сроки и сдача» это один раздел формы («Сдача и подписи»).
const POINTER: Partial<Record<ContentPart, string>> = {
  fields: "/meta_fields",
  forms: "/forms",
  deadlines: "/pack_submission",
  signatures: "/signatures",
  languages: "/langs",
  rules: "/checks_version",
};

export const LegacyVersionPart = ({
  workspaceId,
  versionDir,
  part,
  at,
}: ContentPartProps) => {
  const nav = useContentNav();
  return (
    <LegacyFormPane
      key={part}
      workspaceId={workspaceId}
      path={`${versionDir}/version.yaml`}
      at={at ?? POINTER[part] ?? null}
      onOpenFile={nav.toFile}
    />
  );
};
