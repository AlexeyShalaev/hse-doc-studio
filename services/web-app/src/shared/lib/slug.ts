// Короткое имя латиницей из названия: «Анкета студента» → «anketa_studenta». Нужно формам создания
// (документ, анкета, поле, пак), чтобы человек вводил название, а имя папки и ключ получал сам.

const TRANSLIT: Record<string, string> = {
  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "e",
  ж: "zh",
  з: "z",
  и: "i",
  й: "y",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "h",
  ц: "ts",
  ч: "ch",
  ш: "sh",
  щ: "sch",
  ъ: "",
  ы: "y",
  ь: "",
  э: "e",
  ю: "yu",
  я: "ya",
};

/**
 * `separator` склеивает слова (`_` или `-`). Результат только из строчных латинских букв и цифр;
 * если из названия ничего не вышло (иероглифы), пусто.
 */
export const slugify = (text: string, separator: "_" | "-" = "_"): string => {
  const latin = text
    .toLowerCase()
    .replace(/[а-яё]/gu, (char) => TRANSLIT[char] ?? char);
  return latin
    .replace(/[^a-z0-9]+/g, separator)
    .replace(new RegExp(`^${separator}+|${separator}+$`, "g"), "")
    .slice(0, 48);
};

/** Имя, которого нет среди занятых: при совпадении добавляется номер. */
export const uniqueSlug = (
  base: string,
  taken: readonly string[],
  separator: "_" | "-" = "_",
): string => {
  if (base === "" || !taken.includes(base)) return base;
  for (let n = 2; n < 100; n += 1) {
    const next = `${base}${separator}${String(n)}`;
    if (!taken.includes(next)) return next;
  }
  return base;
};
