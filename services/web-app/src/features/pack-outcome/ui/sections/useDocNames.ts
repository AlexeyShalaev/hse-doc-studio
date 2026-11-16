import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { PackOutcome } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

/** Название документа по id на языке интерфейса; для документа вне ответа остаётся сам id. */
export const useDocNames = (outcome: PackOutcome): ((id: string) => string) => {
  const { i18n } = useTranslation("packOutcome");
  const lang = i18n.language;
  const docs = outcome.documents;
  return useMemo(() => {
    const names = new Map(
      docs.map((d) => [d.id, pickLocalized(d.name, lang, d.id)]),
    );
    return (id: string) => names.get(id) ?? id;
  }, [docs, lang]);
};
