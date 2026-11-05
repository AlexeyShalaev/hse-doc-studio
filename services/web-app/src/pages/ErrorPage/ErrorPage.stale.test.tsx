import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n, useStaleBuildStore } from "@shared/lib";
import { ErrorPage } from "./ErrorPage";

const reload = vi.fn();

const Boom = ({ message }: { message: string }): never => {
  throw new TypeError(message);
};

const mount = (message: string) => {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Boom message={message} />,
        errorElement: <ErrorPage />,
      },
    ],
    { initialEntries: ["/"] },
  );
  return render(
    <I18nextProvider i18n={i18n}>
      <RouterProvider router={router} />
    </I18nextProvider>,
  );
};

beforeEach(async () => {
  reload.mockReset();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, reload },
  });
  window.sessionStorage.clear();
  useStaleBuildStore.setState({ reason: null, screenShown: false });
  await i18n.changeLanguage("ru");
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

describe("граница ошибок маршрута", () => {
  it("ошибка чанка: сообщение о новой версии вместо «Ошибки приложения»", async () => {
    window.sessionStorage.setItem(
      "hds:stale-build-reload-at",
      String(Date.now()),
    );
    mount(
      "Failed to fetch dynamically imported module: https://x.ru/assets/admin-BnUkldQj.js",
    );
    expect(await screen.findByTestId("stale-build-screen")).toBeTruthy();
    expect(screen.getByText("Вышла новая версия Студии")).toBeTruthy();
    expect(screen.queryByText("Ошибка приложения")).toBeNull();
    expect(screen.queryByText(/dynamically imported/)).toBeNull();
    expect(reload).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("stale-build-refresh"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("первая ошибка чанка перезагружает страницу сама", async () => {
    mount("Importing a module script failed.");
    await screen.findByTestId("stale-build-screen");
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("прочие ошибки остаются обычной страницей ошибки", async () => {
    mount("Cannot read properties of undefined");
    expect(await screen.findByText("Ошибка приложения")).toBeTruthy();
    expect(screen.queryByTestId("stale-build-screen")).toBeNull();
    expect(reload).not.toHaveBeenCalled();
  });
});
