import { useTranslation } from "react-i18next";
import type { PackPreviewSwitch } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";

const KNOWN_SWITCHES = new Set([
  "lang",
  "kind",
  "staffing",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
  "nda",
]);

const KNOWN_VALUES = new Set([
  "solo",
  "team2",
  "team3",
  "university",
  "company",
  "none",
  "yes",
  "no",
]);

/** Подпись переключателя: своя у поля анкеты, иначе из словаря. */
export const useSwitchText = () => {
  const { t, i18n } = useTranslation("packStudio");
  return {
    label: (sw: PackPreviewSwitch): string =>
      sw.label
        ? pickLocalized(sw.label, i18n.language, sw.id)
        : KNOWN_SWITCHES.has(sw.id)
          ? t(`preview.switch.${sw.id}`)
          : sw.id.replace(/^meta\./, ""),
    value: (sw: PackPreviewSwitch, value: string): string =>
      sw.id === "lang"
        ? value.toUpperCase()
        : sw.id !== "kind" && KNOWN_VALUES.has(value)
          ? t(`preview.value.${value}`)
          : value,
  };
};
