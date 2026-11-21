import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { isInert } from "./topInputs";

/** «Что это меняет: Документы, Сроки и сдача» и «Влияет на 17 мест». */
export const useAffectsText = (): ((input: OutcomeInput) => string) => {
  const { t } = useTranslation("packSpace");
  return (input) => {
    if (isInert(input)) return t("situation.affectsNone");
    const sections = input.affects
      .map((section) => t(`situation.sections.${section}`))
      .join(", ");
    return [
      t("situation.affects", { sections }),
      input.rules > 0 ? t("situation.readers", { count: input.rules }) : "",
    ]
      .filter((part) => part !== "")
      .join(". ");
  };
};
