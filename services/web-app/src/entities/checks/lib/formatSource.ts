import { i18n, pickLocalized } from "@shared/lib";
import type { LocalizedString } from "@shared/api/types";

// Heading of a rule group. The label is declared by the PACK itself
// (checks/<source>.yaml -> `label`), never by the app: another pack may target a
// different study programme, or a different university altogether, so hardcoding
// names of standards or programmes here would be wrong the moment a second pack
// appears. Falls back to the localized "misc" bucket (a synthetic group with no
// pack file behind it) and finally to the raw source id.
//
// Uses the global i18n instance (pure fn, non-hook) — its consumers use
// `useTranslation` so they re-render and re-call this on an interface-language change.
export const formatSource = (
  source: string,
  label?: LocalizedString,
): string => {
  const fromPack = pickLocalized(label, i18n.language, "");
  if (fromPack) return fromPack;
  if (source === "misc") return i18n.t("checks:source.misc");
  return source;
};
