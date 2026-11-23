import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { partOfKey, type PartId } from "../result/model";
import { isInert } from "./topInputs";

/** Части центра, которые затрагивает условие: разделы сервера без повторов и без проверок (их в центре нет). */
const partsOf = (input: OutcomeInput): PartId[] => [
  ...new Set(
    input.affects.flatMap((section) => {
      const part = partOfKey(`${section}:`);
      return part === null ? [] : [part];
    }),
  ),
];

/** «Что это меняет: Документы, Сроки и сдача» и «Влияет на 17 мест». */
export const useAffectsText = (): ((input: OutcomeInput) => string) => {
  const { t } = useTranslation("packSpace");
  return (input) => {
    if (isInert(input)) return t("situation.affectsNone");
    const sections = partsOf(input)
      .map((part) => t(`result.parts.${part}`))
      .join(", ");
    const text = [
      sections === "" ? "" : t("situation.affects", { sections }),
      input.rules > 0 ? t("situation.readers", { count: input.rules }) : "",
    ]
      .filter((part) => part !== "")
      .join(". ");
    return text === "" ? t("situation.affectsNone") : text;
  };
};
