import type { OnboardingAnswers } from "@entities/onboarding";

type Localized = Record<string, string>;
export type CatalogPack = {
  id: string;
  name: Localized;
  templates: { id: string; name: Localized }[];
};

export type WorkOption = { value: string; label: string };
export type TemplateChoice = {
  packId: string;
  templateId: string;
  label: string;
};

const pick = (text: Localized, lang: string): string =>
  text[lang] ?? text.ru ?? Object.values(text)[0] ?? "";

/** Варианты «над чем работаете» из каталога: по шаблону каждого пака. */
export const workOptions = (
  packs: readonly CatalogPack[],
  lang: string,
): WorkOption[] =>
  packs.flatMap((pack) =>
    pack.templates.map((template) => ({
      value: `${pack.id}/${template.id}`,
      label: `${pick(template.name, lang)} · ${pick(pack.name, lang)}`,
    })),
  );

/**
 * Какой шаблон предложить в конце: выбранный в анкете, иначе курсовая первого пака
 * (самая частая работа), иначе первый шаблон каталога. Каталог пуст — ничего.
 */
export const suggestTemplate = (
  packs: readonly CatalogPack[],
  answers: OnboardingAnswers,
  lang: string,
): TemplateChoice | null => {
  const all = packs.flatMap((pack) =>
    pack.templates.map((template) => ({ pack, template })),
  );
  const [packId, templateId] = (answers.work ?? "").split("/");
  const chosen =
    all.find((x) => x.pack.id === packId && x.template.id === templateId) ??
    all.find((x) => x.template.id === "coursework") ??
    all[0];
  if (!chosen) return null;
  return {
    packId: chosen.pack.id,
    templateId: chosen.template.id,
    label: `${pick(chosen.template.name, lang)} · ${pick(chosen.pack.name, lang)}`,
  };
};
