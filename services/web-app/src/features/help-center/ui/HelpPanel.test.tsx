import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useHelpStore } from "@entities/help";
import { useThemeStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { HelpButton } from "./HelpButton";
import { HelpHost } from "./HelpHost";

const MAP = {
  routes: {
    "/projects/:projectId/submit": ["runbooks/submit-sign"],
    "/wizard": ["runbooks/create-project"],
  },
  articles: [
    {
      key: "runbooks/submit-sign",
      title: "Сдать работу",
      summary: "Комплект на сдачу.",
      url: "/help/ru/runbooks/submit-sign/",
      access: "user",
      routes: ["/projects/:projectId/submit"],
    },
    {
      key: "runbooks/create-project",
      title: "Создать проект",
      summary: "Мастер проекта.",
      url: "/help/ru/runbooks/create-project/",
      access: "user",
      routes: ["/wizard"],
    },
  ],
};

const ARTICLE = {
  key: "runbooks/submit-sign",
  title: "Сдать работу",
  summary: "Комплект на сдачу.",
  url: "/help/ru/runbooks/submit-sign/",
  routes: ["/projects/:projectId/submit"],
  steps: [
    { text: "Откройте **Сдача**." },
    {
      text: "Нажмите **Собрать**.",
      shot: {
        light: "/help/media/a.ru.light.webp",
        dark: "/help/media/a.ru.dark.webp",
      },
    },
  ],
  verified: { at: "2026-11-03", appVersion: "0.3.0" },
};

const fetchMock = vi.fn((url: string) => {
  const body = url.endsWith("help-map.json")
    ? MAP
    : url.includes("/help/runbooks/submit-sign.json")
      ? ARTICLE
      : null;
  return Promise.resolve(
    body
      ? new Response(JSON.stringify(body), { status: 200 })
      : new Response("", { status: 404 }),
  );
});

const mount = (path: string) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <HelpButton />
        <HelpHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("панель справки", () => {
  beforeEach(async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
    await i18n.changeLanguage("ru");
    useThemeStore.setState({ lang: "ru", theme: "light" });
    document.documentElement.setAttribute("data-theme", "light");
  });
  afterEach(() => {
    cleanup();
    act(() => {
      useHelpStore.setState({
        isOpen: false,
        everOpened: false,
        articleKey: undefined,
        focusStep: undefined,
      });
    });
    vi.unstubAllGlobals();
  });

  it("ничего не грузит, пока справку не открыли", () => {
    mount("/projects/p1/submit");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("help-panel")).toBeNull();
  });

  it("клавиша ? открывает статью текущего экрана с кадром своей темы", async () => {
    const user = userEvent.setup();
    mount("/projects/p1/submit");
    await user.keyboard("?");
    expect(
      await screen.findByText("Комплект на сдачу.", undefined, {
        timeout: 5000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByAltText("Шаг 2")).toHaveAttribute(
      "src",
      "/help/media/a.ru.light.webp",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/help/ru/help-map.json",
      expect.anything(),
    );
  });

  it("значок у поля открывает статью на нужном шаге", async () => {
    mount("/projects/p1/submit");
    act(() => {
      useHelpStore.getState().open("runbooks/submit-sign", 2);
    });
    expect(
      await screen.findByTestId("help-step-2", undefined, { timeout: 5000 }),
    ).toHaveClass("is-focused");
  });

  it("экран без статьи говорит об этом, а поиск находит статьи каталога", async () => {
    const user = userEvent.setup();
    mount("/inbox");
    await user.click(screen.getByTestId("help-button"));
    expect(
      await screen.findByTestId("help-no-article", undefined, {
        timeout: 5000,
      }),
    ).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox"), "мастер");
    expect(await screen.findByText("Создать проект")).toBeInTheDocument();
  });

  it("? в поле ввода остаётся символом", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <input aria-label="поле" />
          <HelpHost />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(screen.getByLabelText("поле"));
    await user.keyboard("?");
    expect(useHelpStore.getState().isOpen).toBe(false);
  });
});
