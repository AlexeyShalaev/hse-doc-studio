import { afterEach, describe, expect, it } from "vitest";
import { translitSlug, useCreateWizard } from "./useCreateWizard";

// То же правило, что на сервере (`translit_slug` и `owner_short_name`).
describe("translitSlug", () => {
  it.each([
    ["Иванов Иван Иванович", "ru", "ivanov"],
    ["Ivan Ivanov", "ru", "ivan"],
    ["Ivan Ivanov", "en", "ivanov"],
    ["Maria S. Petrova", "en", "petrova"],
    ["I. I. Ivanov", "en", "ivanov"],
    ["Ivanov I.", "en", "ivanov"],
    ["Ivanov, Ivan", "en", "ivanov"],
    ["Ivanov", "en", "ivanov"],
    ["Иванов Иван Иванович", "en", "ivanov"],
    ["  ", "en", ""],
  ] as const)("%s (%s) -> %s", (name, lang, slug) => {
    expect(translitSlug(name, lang)).toBe(slug);
  });
});

describe("смена языка проекта в мастере", () => {
  afterEach(() => {
    useCreateWizard.getState().reset();
  });

  const author = (name: string, slug: string) => ({
    name,
    group: "",
    topic: "",
    slug,
    managed: true,
  });

  it("пересчитывает подсказанный слаг и не трогает правленный руками", () => {
    const { setField } = useCreateWizard.getState();
    setField("authors", [
      author("Ivan Ivanov", "ivan"),
      author("Petr Petrov", "petya"),
      author("Anna Smirnova", ""),
    ]);
    const slugs = () => useCreateWizard.getState().authors.map((a) => a.slug);

    setField("lang", "en");

    expect(useCreateWizard.getState().lang).toBe("en");
    expect(slugs()).toEqual(["ivanov", "petya", ""]);

    setField("lang", "ru");

    expect(slugs()).toEqual(["ivan", "petya", ""]);
  });
});
