import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import {
  HUNK_KEYS,
  MAIN_TEX,
  PROJECT_ID,
  installFakeConflicts,
  type FakeConflicts,
} from "../testing/fakeConflicts";
import { ConflictScreen } from "./ConflictScreen";

// CodeMirror в jsdom не поднимается: подменяем редактор обычным полем.
vi.mock("@shared/ui/CodeEditor", async () => {
  const { createElement } = await import("react");
  return {
    CodeEditor: ({
      value,
      onChange,
      ariaLabel,
    }: {
      value: string;
      onChange?: (value: string) => void;
      ariaLabel?: string;
    }) =>
      createElement("textarea", {
        "aria-label": ariaLabel,
        value,
        onChange: (event: { target: { value: string } }) => {
          onChange?.(event.target.value);
        },
      }),
  };
});

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

let fake: FakeConflicts;

const renderScreen = () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={[`/projects/${PROJECT_ID}/sync/conflicts`]}
        >
          <ConflictScreen projectId={PROJECT_ID} />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
};

const card = (n: number): HTMLElement =>
  screen.getByRole("group", { name: `Конфликт ${String(n)} из 3` });

const completeButton = (): HTMLElement =>
  screen.getByRole("button", { name: "Завершить и отправить" });

const openFile = async (path: string): Promise<void> => {
  const user = userEvent.setup();
  await user.click(screen.getByTitle(path));
};

const resolveEverything = async (): Promise<void> => {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Всё моё" }));
  await openFile(".hse-studio/forms/title.json");
  await user.click(
    await screen.findByRole("radio", { name: /Оставить мою версию/ }),
  );
  await openFile("images/a.png");
  await user.click(
    await screen.findByRole("radio", { name: /Оставить более новую/ }),
  );
  await openFile("appendix.tex");
  await user.click(
    await screen.findByRole("radio", { name: /Оставить файл с моими/ }),
  );
};

describe("ConflictScreen", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    fake = installFakeConflicts();
  });
  afterEach(() => {
    cleanup();
    fake.restore();
  });

  it("shows the header, the progress and the file groups", async () => {
    renderScreen();
    expect(
      await screen.findByRole("heading", {
        name: "Синхронизация не завершена",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Решено файлов: 0 из 4")).toBeInTheDocument();
    expect(
      screen.getAllByText("Изменения от Анна Петрова").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Требуют решения · 4")).toBeInTheDocument();
    // Автоматически решённые файлы свёрнуты.
    const toggle = screen.getByRole("button", {
      name: /Решено автоматически · 2/,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTitle("references.bib")).toBeNull();
    expect(completeButton()).toBeDisabled();
    expect(screen.getByText(/Осталось решить: 6\./)).toBeInTheDocument();
  });

  it("opens the automatically resolved files on demand", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(
      await screen.findByRole("button", { name: /Решено автоматически · 2/ }),
    );
    await user.click(screen.getByTitle("references.bib"));
    expect(
      await screen.findByText(/объединены автоматически/),
    ).toBeInTheDocument();
  });

  it("shows every hunk of the first file with both sides", async () => {
    renderScreen();
    const first = await screen.findByRole("group", {
      name: "Конфликт 1 из 3",
    });
    expect(
      within(first).getByText("Цель: клиент-серверное приложение."),
    ).toBeInTheDocument();
    expect(
      within(first).getByText("Цель: веб-приложение."),
    ).toBeInTheDocument();
    expect(within(first).getByText("Их (Анна Петрова)")).toBeInTheDocument();
    expect(card(2)).toBeInTheDocument();
    expect(card(3)).toBeInTheDocument();
    // Контекст свёрнут: длинный участок вначале не показан целиком.
    expect(
      screen.getByRole("button", { name: /Показать строки без изменений: 5/ }),
    ).toBeInTheDocument();
  });

  it("marks a hunk as resolved, counts it and moves the focus to the next open hunk", async () => {
    const user = userEvent.setup();
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Взять моё" }));

    expect(within(first).getByText("Выбрано: моё")).toBeInTheDocument();
    expect(screen.getByText("Открыто мест: 2 из 3")).toBeInTheDocument();
    await waitFor(() => {
      expect(card(2)).toHaveFocus();
    });
    expect(
      within(first).getByRole("button", { name: "Взять моё" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("undoes a choice", async () => {
    const user = userEvent.setup();
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Взять их" }));
    await user.click(
      within(first).getByRole("button", { name: "Отменить выбор" }),
    );
    expect(within(first).getByText("Не решено")).toBeInTheDocument();
    expect(screen.getByText("Открыто мест: 3 из 3")).toBeInTheDocument();
  });

  it("walks through the open hunks with N and Shift+N", async () => {
    const user = userEvent.setup();
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Взять моё" }));
    await waitFor(() => {
      expect(card(2)).toHaveFocus();
    });

    await user.keyboard("n");
    await waitFor(() => {
      expect(card(3)).toHaveFocus();
    });
    // Первое место решено: по кругу после третьего идёт второе.
    await user.keyboard("n");
    await waitFor(() => {
      expect(card(2)).toHaveFocus();
    });
    await user.keyboard("{Shift>}n{/Shift}");
    await waitFor(() => {
      expect(card(3)).toHaveFocus();
    });
  });

  it("does not steal the N key from a text field", async () => {
    const user = userEvent.setup();
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Править" }));
    const field = within(first).getByRole("textbox");
    await user.click(field);
    await user.keyboard("n");
    expect(field).toHaveFocus();
  });

  it("accepts a custom text for a hunk and rejects conflict markers", async () => {
    const user = userEvent.setup();
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Править" }));
    const field = within(first).getByRole("textbox");
    await user.clear(field);
    await user.type(field, "<<<<<<< hse:ours");
    expect(within(first).getByRole("alert")).toHaveTextContent(
      "остались метки конфликта",
    );
    expect(
      within(first).getByRole("button", { name: "Применить" }),
    ).toBeDisabled();

    await user.clear(field);
    await user.type(field, "Свой вариант");
    await user.click(within(first).getByRole("button", { name: "Применить" }));
    expect(
      within(first).getByText("Выбрано: свой вариант"),
    ).toBeInTheDocument();
    expect(within(first).getByText("Свой вариант")).toBeInTheDocument();
  });

  it("saves the choices to the server after a pause", async () => {
    const user = userEvent.setup();
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Взять их" }));
    expect(screen.getByText("Сохраняем выбор…")).toBeInTheDocument();
    await waitFor(() => {
      expect(fake.saveCalls).toHaveLength(1);
    });
    expect(fake.saveCalls[0]).toEqual({
      "main.tex": {
        kind: "hunks",
        hunks: { [HUNK_KEYS[0]]: { choice: "theirs" } },
      },
    });
    expect(await screen.findByText("Выбор сохранён")).toBeInTheDocument();
  });

  it("offers a retry when a save fails", async () => {
    const user = userEvent.setup();
    fake.failSave = true;
    renderScreen();
    const first = await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(within(first).getByRole("button", { name: "Взять моё" }));
    expect(await screen.findByText("Выбор не сохранён")).toBeInTheDocument();
    fake.failSave = false;
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByText("Выбор сохранён")).toBeInTheDocument();
    expect(fake.saveCalls.length).toBeGreaterThan(0);
  });

  it("keeps the finish button disabled until every file is resolved", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "Всё моё" }));
    expect(screen.getByText("Решено файлов: 1 из 4")).toBeInTheDocument();
    expect(completeButton()).toBeDisabled();

    await resolveEverything();
    expect(screen.getByText("Решено файлов: 4 из 4")).toBeInTheDocument();
    expect(completeButton()).toBeEnabled();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "4",
    );
  });

  it("shows the result of the choices on the Result tab", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(screen.getByRole("button", { name: "Итог" }));
    expect(
      await screen.findByText("новая строка (result)"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Моё" }));
    expect(await screen.findByText("новая строка (ours)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Их" }));
    expect(
      await screen.findByText("новая строка (theirs)"),
    ).toBeInTheDocument();
  });

  it("edits the file by hand, but not with conflict markers in it", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await user.click(screen.getByRole("button", { name: "Править вручную" }));
    const editor = await screen.findByRole("textbox", {
      name: "Итоговый текст файла main.tex",
    });
    // Начинаем с файла, каким он получится сейчас: нерешённое остаётся моим.
    expect((editor as HTMLTextAreaElement).value).toContain(
      "Цель: клиент-серверное приложение.",
    );

    await user.type(editor, "\n<<<<<<< hse:ours");
    expect(screen.getByRole("alert")).toHaveTextContent("метки конфликта");
    expect(
      screen.getByRole("button", { name: "Использовать этот текст" }),
    ).toBeDisabled();

    await user.clear(editor);
    await user.type(editor, "Готовый текст");
    await user.click(
      screen.getByRole("button", { name: "Использовать этот текст" }),
    );
    expect(screen.getByText("Решено файлов: 1 из 4")).toBeInTheDocument();
    expect(screen.getByText("Правлено вручную")).toBeInTheDocument();
    await waitFor(() => {
      expect(fake.drafts["main.tex"]).toEqual({
        kind: "text",
        content: "Готовый текст",
      });
    });

    // Выбор по частям недоступен, пока не вернёшься к нему.
    await user.click(screen.getByRole("button", { name: "По частям" }));
    await user.click(
      screen.getByRole("button", { name: "Вернуться к выбору по частям" }),
    );
    expect(screen.getByText("Решено файлов: 0 из 4")).toBeInTheDocument();
  });

  it("picks a version of a file as a whole", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await openFile("images/a.png");
    const radios = await screen.findAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(screen.getByText("рекомендуем")).toBeInTheDocument();
    await user.click(
      screen.getByRole("radio", { name: /Взять версию из репозитория/ }),
    );
    expect(screen.getByText("Решено файлов: 1 из 4")).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Взять версию из репозитория/ }),
    ).toBeChecked();
  });

  it("describes a deleted file in its own words", async () => {
    renderScreen();
    await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    await openFile("appendix.tex");
    expect(
      await screen.findByText("В репозитории файл удалили, а ты его изменил."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Файла нет").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("radio", { name: /Удалить файл, как в репозитории/ }),
    ).toBeInTheDocument();
  });

  it("moves between the files with the arrow keys", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByRole("group", { name: "Конфликт 1 из 3" });
    const rows = screen
      .getAllByRole("button")
      .filter((b) => b.hasAttribute("data-file-row"));
    expect(rows).toHaveLength(4);
    rows[0]?.focus();
    await user.keyboard("{ArrowDown}");
    expect(rows[1]).toHaveFocus();
    await user.keyboard("{End}");
    expect(rows[3]).toHaveFocus();
    await user.keyboard("{Home}");
    expect(rows[0]).toHaveFocus();
  });

  describe("finishing", () => {
    it("sends the choices, shows the progress and opens the history", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      await user.click(completeButton());

      expect(await screen.findByText("Применяем решения")).toBeInTheDocument();
      expect(fake.resolveCalls).toHaveLength(1);
      expect(fake.resolveCalls[0]?.fingerprint).toBe("fp-1");
      expect(Object.keys(fake.resolveCalls[0]?.resolutions ?? {})).toEqual(
        expect.arrayContaining([
          "main.tex",
          ".hse-studio/forms/title.json",
          "images/a.png",
          "appendix.tex",
        ]),
      );
      expect(screen.getByText("Объединяем файлы")).toBeInTheDocument();
      expect(screen.getByText("Отправляем в репозиторий")).toBeInTheDocument();

      fake.finishOperation("succeeded");
      await waitFor(
        () => {
          expect(screen.getByTestId("location").textContent).toBe(
            `/projects/${PROJECT_ID}/versions`,
          );
        },
        { timeout: 4000 },
      );
    });

    it("keeps the choices and reloads the list when the plan is outdated", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      fake.rebuildPlan("fp-2");
      await user.click(completeButton());

      expect(
        await screen.findByText(/Пока ты разбирал, проект или репозиторий/),
      ).toBeInTheDocument();
      // Выборы не потеряны: кнопка снова доступна, новый отпечаток уйдёт в запрос.
      await waitFor(() => {
        expect(screen.getByText("Решено файлов: 4 из 4")).toBeInTheDocument();
      });
      expect(completeButton()).toBeEnabled();
      await user.click(completeButton());
      await waitFor(() => {
        expect(fake.resolveCalls).toHaveLength(2);
      });
      expect(fake.resolveCalls[1]?.fingerprint).toBe("fp-2");
      expect(await screen.findByText("Применяем решения")).toBeInTheDocument();
    });

    it("drops the choices for hunks that the new plan no longer has", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      await waitFor(() => {
        expect(fake.drafts["main.tex"]).toBeDefined();
      });
      // Новый план: у main.tex осталось два места, третьего больше нет.
      const files = fake.session.files.map((f) =>
        f.path === "main.tex" ? { ...f, hunks: 2, open_hunks: 2 } : f,
      );
      fake.details["main.tex"] = {
        ...MAIN_TEX,
        segments: MAIN_TEX.segments.filter(
          (s) => s.type === "clean" || s.key !== HUNK_KEYS[2],
        ),
      };
      fake.rebuildPlan("fp-2", files);
      await user.click(completeButton());
      await screen.findByText(/Пока ты разбирал/);
      await waitFor(() => {
        expect(screen.getByText("Решено файлов: 4 из 4")).toBeInTheDocument();
      });
      await waitFor(() => {
        const draft = fake.saveCalls.at(-1)?.["main.tex"];
        expect(draft?.kind === "hunks" && Object.keys(draft.hunks)).toEqual([
          HUNK_KEYS[0],
          HUNK_KEYS[1],
        ]);
      });
    });

    it("shows a failure with a retry and a way back", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      await user.click(completeButton());
      await screen.findByText("Применяем решения");
      fake.finishOperation("failed", "merged", "merge");

      expect(
        await screen.findByText("Не получилось завершить", undefined, {
          timeout: 4000,
        }),
      ).toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent(
        /ушёл вперёд|Репозиторий/,
      );
      await user.click(
        screen.getByRole("button", { name: "Вернуться к конфликтам" }),
      );
      expect(
        await screen.findByText("Решено файлов: 4 из 4"),
      ).toBeInTheDocument();
      expect(completeButton()).toBeEnabled();
    });

    it("leaves for the history when a retry finds nothing to resolve", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      await user.click(completeButton());
      await screen.findByText("Применяем решения");
      fake.finishOperation("failed", "merged", "merge");
      await screen.findByText("Не получилось завершить", undefined, {
        timeout: 4000,
      });
      // Слияние уже применено, сеанс закрыт: сервер отвечает 404.
      const { ApiError } = await import("@shared/api");
      fake.failResolveWith = new ApiError(
        "Нет конфликтов",
        "no_conflicts",
        404,
      );
      await user.click(screen.getByRole("button", { name: "Повторить" }));
      await waitFor(() => {
        expect(screen.getByTestId("location").textContent).toBe(
          `/projects/${PROJECT_ID}/versions`,
        );
      });
    });

    it("offers only the history after a failed push", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      await user.click(completeButton());
      await screen.findByText("Применяем решения");
      fake.finishOperation("failed");

      await screen.findByText("Не получилось завершить", undefined, {
        timeout: 4000,
      });
      expect(screen.queryByRole("button", { name: "Повторить" })).toBeNull();
      expect(
        screen.queryByRole("button", { name: "Вернуться к конфликтам" }),
      ).toBeNull();
      expect(screen.getByText(/Конфликтов больше нет/)).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Открыть историю" }));
      await waitFor(() => {
        expect(screen.getByTestId("location").textContent).toBe(
          `/projects/${PROJECT_ID}/versions`,
        );
      });
    });

    it("explains an error the server gave instead of an operation", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await resolveEverything();
      const { ApiError } = await import("@shared/api");
      fake.failResolveWith = new ApiError(
        "Нужно указать автора",
        "profile_required",
        409,
      );
      await user.click(completeButton());
      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(completeButton()).toBeEnabled();
    });
  });

  describe("cancelling the merge", () => {
    it("asks first and names the saved version", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await user.click(
        screen.getByRole("button", { name: "Отменить слияние" }),
      );
      const dialog = await screen.findByRole("dialog");
      expect(dialog).toHaveTextContent("Дописан раздел");
      await user.click(
        within(dialog).getByRole("button", { name: "Продолжить разбор" }),
      );
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(fake.aborted).toBe(false);
    });

    it("ignores the N key pressed inside the confirmation dialog", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await user.click(
        screen.getByRole("button", { name: "Отменить слияние" }),
      );
      const dialog = await screen.findByRole("dialog");
      const keep = within(dialog).getByRole("button", {
        name: "Продолжить разбор",
      });
      keep.focus();
      await user.keyboard("n");
      expect(keep).toHaveFocus();
    });

    it("keeps saving choices after a failed cancel", async () => {
      const user = userEvent.setup();
      const { ApiError } = await import("@shared/api");
      const { gitSyncApi } = await import("@entities/git-sync");
      vi.mocked(gitSyncApi.abortConflicts).mockRejectedValueOnce(
        new ApiError("Сервер недоступен", "internal", 500),
      );
      renderScreen();
      const first = await screen.findByRole("group", {
        name: "Конфликт 1 из 3",
      });
      await user.click(
        screen.getByRole("button", { name: "Отменить слияние" }),
      );
      const dialog = await screen.findByRole("dialog");
      await user.click(
        within(dialog).getByRole("button", { name: "Отменить слияние" }),
      );
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(fake.aborted).toBe(false);

      await user.click(
        within(first).getByRole("button", { name: "Взять моё" }),
      );
      await waitFor(() => {
        expect(fake.saveCalls.length).toBeGreaterThan(0);
      });
    });

    it("cancels the merge and opens the history", async () => {
      const user = userEvent.setup();
      renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      await user.click(
        screen.getByRole("button", { name: "Отменить слияние" }),
      );
      const dialog = await screen.findByRole("dialog");
      await user.click(
        within(dialog).getByRole("button", { name: "Отменить слияние" }),
      );
      await waitFor(() => {
        expect(screen.getByTestId("location").textContent).toBe(
          `/projects/${PROJECT_ID}/versions`,
        );
      });
      expect(fake.aborted).toBe(true);
    });
  });

  describe("states", () => {
    it("shows that there is nothing to resolve", async () => {
      fake.aborted = true;
      renderScreen();
      expect(await screen.findByText("Конфликтов нет")).toBeInTheDocument();
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "Открыть историю" }));
      expect(screen.getByTestId("location").textContent).toBe(
        `/projects/${PROJECT_ID}/versions`,
      );
    });

    it("shows that there is nothing to resolve when the session disappears", async () => {
      const { client } = renderScreen();
      await screen.findByRole("group", { name: "Конфликт 1 из 3" });
      fake.aborted = true;
      await client.invalidateQueries();
      expect(await screen.findByText("Конфликтов нет")).toBeInTheDocument();
    });

    it("reports a failed load and retries", async () => {
      const { ApiError } = await import("@shared/api");
      const { gitSyncApi } = await import("@entities/git-sync");
      vi.mocked(gitSyncApi.getConflicts).mockRejectedValueOnce(
        new ApiError("Сервер недоступен", "internal", 500),
      );
      renderScreen();
      expect(
        await screen.findByText("Не удалось загрузить конфликты"),
      ).toBeInTheDocument();
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "Повторить" }));
      expect(
        await screen.findByRole("group", { name: "Конфликт 1 из 3" }),
      ).toBeInTheDocument();
    });

    it("shows a loading state first", () => {
      renderScreen();
      expect(screen.getByText("Загружаем конфликты…")).toBeInTheDocument();
    });

    it("reports a file whose contents cannot be loaded", async () => {
      const { ApiError } = await import("@shared/api");
      const { gitSyncApi } = await import("@entities/git-sync");
      vi.mocked(gitSyncApi.getConflictFile).mockRejectedValue(
        new ApiError("Ошибка", "internal", 500),
      );
      renderScreen();
      expect(
        await screen.findByText("Не удалось загрузить содержимое файла."),
      ).toBeInTheDocument();
    });

    it("speaks English when the interface language is English", async () => {
      await i18n.changeLanguage("en");
      renderScreen();
      expect(
        await screen.findByRole("heading", { name: "Sync is not finished" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Files resolved: 0 of 4")).toBeInTheDocument();
      expect(
        await screen.findByRole("group", { name: "Conflict 1 of 3" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Finish and send" }),
      ).toBeDisabled();
      await i18n.changeLanguage("ru");
    });
  });
});
