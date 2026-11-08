import { useTranslation } from "react-i18next";
import { kindsText, type BuildBlock } from "@entities/compile";

/** Заголовок и причина недоступной сборки: «раннеров нет» или «нет раннера для …». */
export const useBuildBlockText = (
  block: BuildBlock,
): { title: string; reason: string } => {
  const { t } = useTranslation("documents");
  const title = t("compile.unavailable.title");
  const kinds = kindsText(t, block.tags);
  // Раннер с нужным тегом есть, но на паузе или не в сети: называем именно это.
  if (block.cause !== undefined && block.cause !== "no_runner") {
    return {
      title,
      reason: t(`compile.unavailable.cause.${block.cause}`, { kinds }),
    };
  }
  if (block.reason === "no_runners") {
    return { title, reason: t("compile.unavailable.noRunners") };
  }
  return { title, reason: t("compile.unavailable.noRunnerForTags", { kinds }) };
};
