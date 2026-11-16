import type { TFunction } from "i18next";

const AUTHOR = /^author(\d+)$/;

/** Подпись персоны или слота: «Автор 2», «Руководитель»; незнакомый id остаётся как есть. */
export const personaLabel = (
  t: TFunction<"packOutcome">,
  persona: string,
): string => {
  const num = AUTHOR.exec(persona)?.[1];
  if (num) return t("participants.authorN", { n: num });
  return t(`participants.role.${persona}`, { defaultValue: persona });
};
