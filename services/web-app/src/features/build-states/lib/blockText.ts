import { useTranslation } from "react-i18next";
import type { BuildBlock } from "@entities/compile";

const KNOWN_KINDS = new Set(["tex", "office"]);

/** Заголовок и причина недоступной сборки: «раннеров нет» или «нет раннера для …». */
export const useBuildBlockText = (
  block: BuildBlock,
): { title: string; reason: string } => {
  const { t } = useTranslation("documents");
  const title = t("compile.unavailable.title");
  if (block.reason === "no_runners") {
    return { title, reason: t("compile.unavailable.noRunners") };
  }
  const kinds = block.tags
    .map((tag) =>
      KNOWN_KINDS.has(tag) ? t(`compile.unavailable.kind.${tag}`) : tag,
    )
    .join(t("compile.unavailable.kindSeparator"));
  return { title, reason: t("compile.unavailable.noRunnerForTags", { kinds }) };
};
