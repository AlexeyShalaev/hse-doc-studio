import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FileResolution, JsonFieldConflict } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import type { JsonDetail } from "../model/conflictModel";
import { JsonFieldResolver } from "./JsonFieldResolver";

const field = (
  pointer: string,
  overrides: Partial<JsonFieldConflict> = {},
): JsonFieldConflict => ({
  pointer,
  label: null,
  type: "scalar",
  base: "Исходное значение",
  ours: "Моё значение",
  theirs: "Их значение",
  allowed: ["mine", "theirs"],
  status: "conflict",
  ...overrides,
});

const DETAIL: JsonDetail = {
  kind: "json",
  fields: [
    field("/answers/title", { label: "Тема работы" }),
    field("/answers/keywords", {
      label: "Ключевые слова",
      type: "list",
      base: ["git"],
      ours: ["git", "синхронизация"],
      theirs: ["git", "LaTeX"],
      allowed: ["mine", "theirs", "union"],
    }),
    field("/meta/unknown_key", { base: 1, ours: 2, theirs: 3 }),
    field("/answers/year", {
      label: "Год защиты",
      base: 2025,
      ours: 2025,
      theirs: 2026,
      status: "auto",
    }),
    field("/answers/city", {
      label: "Город",
      base: "Москва",
      ours: "Казань",
      theirs: "Москва",
      status: "auto",
    }),
  ],
};

const handlers = () => ({
  onChoose: vi.fn(),
  onClear: vi.fn(),
  onChooseAll: vi.fn(),
  onNextFile: vi.fn(),
});

const renderResolver = (
  resolution: FileResolution | null = null,
  overrides: Partial<{ detail: JsonDetail; hasNextFile: boolean }> = {},
) => {
  const fns = handlers();
  render(
    <JsonFieldResolver
      detail={overrides.detail ?? DETAIL}
      resolution={resolution}
      theirsLabel="Их (Анна)"
      hasNextFile={overrides.hasNextFile ?? true}
      {...fns}
    />,
  );
  return fns;
};

const card = (name: string): HTMLElement =>
  screen.getByRole("radiogroup", { name: new RegExp(name) });

describe("JsonFieldResolver", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("shows a card per disputed field with the was, mine and theirs values", () => {
    renderResolver();
    const title = card("Тема работы");
    expect(within(title).getByText("Было")).toBeInTheDocument();
    expect(within(title).getByText("Моё")).toBeInTheDocument();
    expect(within(title).getByText("Их (Анна)")).toBeInTheDocument();
    expect(within(title).getByText("Моё значение")).toBeInTheDocument();
    expect(within(title).getByText("Их значение")).toBeInTheDocument();
    expect(screen.getByText("Открыто полей: 3 из 3")).toBeInTheDocument();
  });

  it("falls back to the pointer when the server gave no label", () => {
    renderResolver();
    const group = card("/meta/unknown_key");
    expect(within(group).getByText("/meta/unknown_key")).toBeInTheDocument();
    // Число показано моноширинным значением.
    expect(within(group).getByText("2")).toBeInTheDocument();
    // Указатель рядом с понятным названием тоже виден.
    expect(
      within(card("Тема работы")).getByText("/answers/title"),
    ).toBeInTheDocument();
  });

  it("reports a choice of each side", async () => {
    const user = userEvent.setup();
    const fns = renderResolver();
    await user.click(
      within(card("Тема работы")).getByRole("radio", { name: /: Моё$/ }),
    );
    expect(fns.onChoose).toHaveBeenLastCalledWith("/answers/title", "mine");
    await user.click(
      within(card("Тема работы")).getByRole("radio", {
        name: /: Их \(Анна\)$/,
      }),
    );
    expect(fns.onChoose).toHaveBeenLastCalledWith("/answers/title", "theirs");
  });

  it("offers to combine a list and shows what the result will be", async () => {
    const user = userEvent.setup();
    const fns = renderResolver();
    const keywords = card("Ключевые слова");
    const union = within(keywords).getByRole("radio", {
      name: /: Объединить$/,
    });
    // Объединение: мои значения, затем чужие, без повторов.
    const cell = union.closest("label");
    const items = within(cell as HTMLElement)
      .getAllByRole("listitem")
      .map((li) => li.textContent.replace(/\s*\(новое\)$/, ""));
    expect(items).toEqual(["git", "синхронизация", "LaTeX"]);
    await user.click(union);
    expect(fns.onChoose).toHaveBeenCalledWith("/answers/keywords", "union");
    // Для обычного поля такого варианта нет.
    expect(
      within(card("Тема работы")).queryByRole("radio", {
        name: /Объединить/,
      }),
    ).toBeNull();
  });

  it("marks the list items that are new compared with the original", () => {
    renderResolver();
    const keywords = card("Ключевые слова");
    const fresh = within(keywords)
      .getAllByRole("listitem")
      .filter((li) => li.getAttribute("data-new") === "true")
      .map((li) => li.textContent.trim());
    expect(fresh.some((text) => text.startsWith("синхронизация"))).toBe(true);
    expect(fresh.some((text) => text.startsWith("LaTeX"))).toBe(true);
    expect(fresh.some((text) => text.startsWith("git"))).toBe(false);
  });

  it("shows the chosen field as resolved and takes the choice back", async () => {
    const user = userEvent.setup();
    const fns = renderResolver({
      kind: "fields",
      fields: { "/answers/title": { choice: "theirs" } },
    });
    const title = card("Тема работы");
    expect(within(title).getByText("Выбрано: их")).toBeInTheDocument();
    expect(
      within(title).getByRole("radio", { name: /: Их \(Анна\)$/ }),
    ).toBeChecked();
    expect(
      within(title).getByRole("radio", { name: /: Моё$/ }),
    ).not.toBeChecked();
    expect(screen.getByText("Открыто полей: 2 из 3")).toBeInTheDocument();
    expect(
      within(card("Ключевые слова")).getByText("Не решено"),
    ).toBeInTheDocument();
    await user.click(
      within(title).getByRole("button", { name: "Отменить выбор" }),
    );
    expect(fns.onClear).toHaveBeenCalledWith("/answers/title");
  });

  it("treats a whole-file choice as a choice of every field", () => {
    renderResolver({ kind: "file", choice: "mine" });
    expect(
      within(card("Тема работы")).getByRole("radio", { name: /: Моё$/ }),
    ).toBeChecked();
    expect(
      screen.getByText("Все поля в этом файле решены"),
    ).toBeInTheDocument();
  });

  it("takes everything from one side with a single click", async () => {
    const user = userEvent.setup();
    const fns = renderResolver();
    await user.click(screen.getByRole("button", { name: "Всё моё" }));
    expect(fns.onChooseAll).toHaveBeenLastCalledWith("mine");
    await user.click(screen.getByRole("button", { name: "Всё их" }));
    expect(fns.onChooseAll).toHaveBeenLastCalledWith("theirs");
  });

  it("keeps the merged fields collapsed and says whose value was taken", async () => {
    const user = userEvent.setup();
    renderResolver();
    const toggle = screen.getByRole("button", {
      name: "Слито автоматически: 2 поля",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Год защиты")).toBeNull();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Год защиты")).toBeInTheDocument();
    expect(screen.getByText("взято их")).toBeInTheDocument();
    expect(screen.getByText("взято моё")).toBeInTheDocument();
    // Автоматические поля не выбираются.
    expect(screen.queryAllByRole("radiogroup")).toHaveLength(3);
  });

  it("offers the next file once every field is decided", async () => {
    const user = userEvent.setup();
    const fns = renderResolver({
      kind: "fields",
      fields: {
        "/answers/title": { choice: "mine" },
        "/answers/keywords": { choice: "union" },
        "/meta/unknown_key": { choice: "theirs" },
      },
    });
    expect(
      screen.getByText("Все поля в этом файле решены"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "К следующему файлу" }),
    );
    expect(fns.onNextFile).toHaveBeenCalled();
  });

  it("does not offer the next file when nothing else is open", () => {
    renderResolver({ kind: "file", choice: "theirs" }, { hasNextFile: false });
    expect(
      screen.queryByRole("button", { name: "К следующему файлу" }),
    ).toBeNull();
  });

  it("renders every kind of value in words, not as an empty cell", () => {
    renderResolver(null, {
      detail: {
        kind: "json",
        fields: [
          field("/a", { base: null, ours: "", theirs: true }),
          field("/b", {
            type: "presence",
            base: null,
            ours: false,
            theirs: null,
          }),
          field("/c", { base: [], ours: { x: 1 }, theirs: [] }),
        ],
      },
    });
    // «Было» (нет значения) и «моё» (пустая строка) оба названы словом.
    expect(within(card("/a")).getAllByText("(пусто)")).toHaveLength(2);
    expect(within(card("/a")).getByText("да")).toBeInTheDocument();
    expect(within(card("/b")).getAllByText("(нет)")).toHaveLength(2);
    expect(within(card("/b")).getByText("нет")).toBeInTheDocument();
    expect(within(card("/c")).getAllByText("(пустой список)")).toHaveLength(2);
    expect(within(card("/c")).getByText(/"x": 1/)).toBeInTheDocument();
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    renderResolver();
    expect(screen.getByText("Fields left: 3 of 3")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Merged automatically: 2 fields" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "All mine" }),
    ).toBeInTheDocument();
  });
});
