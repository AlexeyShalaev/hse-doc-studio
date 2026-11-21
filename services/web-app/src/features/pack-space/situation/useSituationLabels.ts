import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { STANDARD_INPUTS, isToken } from "@features/pack-outcome/lib/inputs";

/**
 * Подписи условий и их значений. Первой берётся подпись из пака (`label`, ru и en), затем
 * словарь для стандартных условий (язык, вид работы, число авторов, руководители) и для «да» и
 * «нет», иначе сам идентификатор или значение. Условий конкретного пака здесь нет.
 */
export const useSituationLabels = () => {
  const { t, i18n } = useTranslation("packSpace");
  const lang = i18n.language;

  const inputLabel = useCallback(
    (input: OutcomeInput): string => {
      const own = pickLocalized(input.label ?? undefined, lang, "");
      if (own !== "") return own;
      const key = `situation.std.${input.id}`;
      return STANDARD_INPUTS.includes(input.id) &&
        i18n.exists(key, { ns: "packSpace" })
        ? t(key)
        : input.id;
    },
    [i18n, lang, t],
  );

  const valueLabel = useCallback(
    (input: OutcomeInput, value: string): string => {
      const own = pickLocalized(
        input.values.find((item) => item.value === value)?.label ?? undefined,
        lang,
        "",
      );
      if (own !== "") return own;
      if (input.type === "bool" && (value === "yes" || value === "no")) {
        return t(`situation.${value}`);
      }
      const key = `situation.values.${input.id}.${value}`;
      return STANDARD_INPUTS.includes(input.id) &&
        isToken(value) &&
        i18n.exists(key, { ns: "packSpace" })
        ? t(key)
        : value;
    },
    [i18n, lang, t],
  );

  return { inputLabel, valueLabel };
};
