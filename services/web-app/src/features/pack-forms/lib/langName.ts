// Название языка по коду («ru» это «Русский»): человек видит язык, а не код файла. Названия даёт
// браузер (Intl.DisplayNames) на языке интерфейса; без него или для странного кода остаётся код.

const cache = new Map<string, Intl.DisplayNames | null>();

const namesFor = (uiLang: string): Intl.DisplayNames | null => {
  if (!cache.has(uiLang)) {
    try {
      cache.set(uiLang, new Intl.DisplayNames([uiLang], { type: "language" }));
    } catch {
      cache.set(uiLang, null);
    }
  }
  return cache.get(uiLang) ?? null;
};

export const langName = (code: string, uiLang: string): string => {
  let name: string | undefined;
  try {
    name = namesFor(uiLang)?.of(code);
  } catch {
    name = undefined;
  }
  if (!name || name.toLowerCase() === code.toLowerCase()) return code;
  return name.charAt(0).toUpperCase() + name.slice(1);
};
