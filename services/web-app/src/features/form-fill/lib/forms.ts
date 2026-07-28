import type { FormAnswers, FormFieldDef, FormSection } from "@entities/form";

export type LocalizedMap = Record<string, string> | null | undefined;

/** Pick a localized string, preferring the active lang then ru/en. */
export const loc = (map: LocalizedMap, lang = "ru"): string => {
  if (!map) return "";
  return map[lang] ?? map.ru ?? map.en ?? Object.values(map)[0] ?? "";
};

/** A field is shown only when its `visible_if` condition matches the answers. */
export const isFieldVisible = (
  field: FormFieldDef,
  answers: FormAnswers,
): boolean => {
  const cond = field.visible_if;
  if (!cond) return true;
  return answers[cond.field] === cond.equals;
};

/** Seed initial answers from the schema's declared defaults. */
export const computeDefaults = (
  sections: readonly FormSection[],
): FormAnswers => {
  const out: FormAnswers = {};
  for (const section of sections) {
    for (const field of section.fields) {
      if (field.type === "markdown") continue;
      if (field.type === "table") {
        out[field.id] = [];
        continue;
      }
      if (field.type === "multiselect") {
        if (Array.isArray(field.default)) {
          out[field.id] = field.default;
        } else {
          const checked = field.options
            .filter((o) => o.default)
            .map((o) => o.id);
          if (checked.length > 0) out[field.id] = checked;
        }
        continue;
      }
      if (field.default !== undefined && field.default !== null) {
        out[field.id] = field.default;
      }
    }
  }
  return out;
};

/** Defaults first, then overlay saved answers so persisted values win. */
export const mergeAnswers = (
  defaults: FormAnswers,
  saved: FormAnswers,
): FormAnswers => ({ ...defaults, ...saved });
