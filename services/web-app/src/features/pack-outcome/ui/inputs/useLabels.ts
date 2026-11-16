import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { STANDARD_INPUTS, isToken } from "../../lib/inputs";

/**
 * Подписи вводных и значений. Первым берётся подпись из пака (`label`, ru и en), затем словарь
 * интерфейса для стандартных вводных (язык, вид работы, состав, руководители) и для да и нет,
 * иначе сам идентификатор или значение. Ни одной подписи в клиенте не привязано к конкретному паку.
 */
export const useInputLabels = () => {
  const { t, i18n } = useTranslation("packOutcome");
  const lang = i18n.language;

  const inputLabel = useCallback(
    (input: OutcomeInput): string => {
      const own = pickLocalized(input.label ?? undefined, lang, "");
      if (own !== "") return own;
      const key = `inputs.std.${input.id}`;
      if (
        STANDARD_INPUTS.includes(input.id) &&
        i18n.exists(key, { ns: "packOutcome" })
      ) {
        return t(key);
      }
      return input.id;
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
        return t(`inputs.bool.${value}`);
      }
      const key = `inputs.values.${input.id}.${value}`;
      if (
        STANDARD_INPUTS.includes(input.id) &&
        isToken(value) &&
        i18n.exists(key, { ns: "packOutcome" })
      ) {
        return t(key);
      }
      return value;
    },
    [i18n, lang, t],
  );

  return { inputLabel, valueLabel };
};
