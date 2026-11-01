import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { installServerDemo } from "../../../app/demo";
import {
  activateServerScenario,
  enableServerDemo,
} from "../../../app/demo/server";
import { ProjectImportDialog } from "./ProjectImportDialog";

// Окно импорта поверх демо-транспорта: те же запросы, что уйдут настоящему бэкенду.
// Исход выбирает имя файла (см. демо-маршрут POST /projects/import).

const Where = () => <div data-testid="where">{useLocation().pathname}</div>;

const mount = (onClose = () => undefined) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          })
        }
      >
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route
              path="*"
              element={
                <>
                  <ProjectImportDialog isOpen onClose={onClose} />
                  <Where />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const zip = (name: string) =>
  new File([new Uint8Array(2048)], name, { type: "application/zip" });

const choose = async (name: string) => {
  const user = userEvent.setup();
  await user.upload(
    await screen.findByTestId("project-import-input"),
    zip(name),
  );
  return user;
};

// Демо-транспорт растягивает отправку файла на несколько шагов: ждём дольше обычного.
const SLOW = { timeout: 6000 };

describe(
  "окно «Импорт проекта из локальной Студии»",
  { timeout: 15_000 },
  () => {
    beforeAll(() => {
      installServerDemo();
      enableServerDemo();
    });
    beforeEach(async () => {
      await i18n.changeLanguage("ru");
      activateServerScenario("student_ready");
    });
    afterEach(cleanup);

    it("без файла импортировать нельзя, подсказка объясняет, что архивировать", async () => {
      mount();
      expect(
        await screen.findByTestId("project-import-dropzone"),
      ).toBeVisible();
      expect(
        screen.getByRole("button", { name: "Импортировать" }),
      ).toBeDisabled();
      expect(
        screen.getByText(/вместе со скрытой папкой \.hse-studio/),
      ).toBeVisible();
    });

    it("не zip отклоняется на месте", async () => {
      mount();
      const user = userEvent.setup({ applyAccept: false });
      await user.upload(
        await screen.findByTestId("project-import-input"),
        new File(["x"], "notes.txt"),
      );
      expect(
        await screen.findByText("Нужен файл с расширением .zip."),
      ).toBeVisible();
    });

    it("успех: итог с числами, затем переход в проект", async () => {
      mount();
      const user = await choose("thesis.zip");
      expect(screen.getByTestId("project-import-file")).toHaveTextContent(
        "thesis.zip",
      );
      await user.click(screen.getByRole("button", { name: "Импортировать" }));

      const done = await screen.findByTestId("project-import-done", {}, SLOW);
      expect(done).toHaveTextContent("Проект импортирован");
      expect(done).toHaveTextContent("42 файла");
      expect(done).toHaveTextContent("2 чата");
      await user.click(screen.getByRole("button", { name: "Открыть проект" }));
      await waitFor(() => {
        expect(screen.getByTestId("where").textContent).toMatch(
          /^\/projects\/p_demo\d+\/documents$/,
        );
      });
    });

    it("предупреждения и новый id показываются в итоге", async () => {
      mount();
      const user = await choose("remote-again.zip");
      await user.click(screen.getByRole("button", { name: "Импортировать" }));

      const done = await screen.findByTestId("project-import-done", {}, SLOW);
      expect(done).toHaveTextContent("уже занят");
      expect(done).toHaveTextContent("доступа к нему на сервере нет");
      expect(done).toHaveTextContent("6 записей");
    });

    it.each([
      [
        "evil.zip",
        "Архив отклонён: в нём недопустимые пути, ссылки или шифрование.",
      ],
      ["huge.zip", "Проект больше допустимого размера."],
      ["empty.zip", "В архиве нет проекта Студии."],
      ["newer.zip", "Проект записан более новой версией Студии."],
      ["broken.zip", "Это не zip-архив или он повреждён."],
    ])("отказ %s показан в окне, файл можно заменить", async (name, text) => {
      mount();
      const user = await choose(name);
      await user.click(screen.getByRole("button", { name: "Импортировать" }));

      const alert = await screen.findByRole("alert", {}, SLOW);
      expect(alert).toHaveTextContent("Не удалось импортировать");
      expect(alert).toHaveTextContent(text);
      expect(screen.getByRole("button", { name: "Заменить" })).toBeVisible();
      expect(
        screen.getByRole("button", { name: "Импортировать" }),
      ).toBeEnabled();
    });

    it("на английском тексты отказа и итога английские", async () => {
      await i18n.changeLanguage("en");
      mount();
      const user = await choose("evil.zip");
      await user.click(screen.getByRole("button", { name: "Import" }));
      expect(await screen.findByRole("alert", {}, SLOW)).toHaveTextContent(
        "The archive was rejected",
      );
    });
  },
);
