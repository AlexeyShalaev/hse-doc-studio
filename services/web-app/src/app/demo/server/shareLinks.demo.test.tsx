import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { ShareLinksSection } from "@features/share-links";
import { ShareLinkPage } from "@pages/ShareLinkPage";
import { i18n, useToastStore } from "@shared/lib";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { getServerWorld } from "./routes";

// Ссылки доступа поверх демо-транспорта: те же запросы и схемы, что у настоящего API.

const mount = (ui: React.ReactNode, path = "/") =>
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
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/s/:token" element={<ShareLinkPage />} />
            <Route
              path="/projects/:projectId/*"
              element={<div data-testid="landed">landed</div>}
            />
            <Route path="*" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

beforeAll(() => {
  installServerDemo();
  enableServerDemo();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  useToastStore.getState().clear();
});
afterEach(cleanup);

describe("демо: ссылки доступа", () => {
  it("владелец видит ссылки и создаёт новую с копируемым адресом", async () => {
    activateServerScenario("student_ready");
    mount(<ShareLinksSection projectId="p_01hxa1c4de" myRole="owner" />);
    expect(
      await screen.findByTestId("share-link-row-lnk_demo_reader"),
    ).toBeTruthy();
    expect(screen.queryByTestId("share-link-row-lnk_demo_old")).toBeNull();
    await userEvent.click(screen.getByTestId("share-link-create"));
    const form = await screen.findByTestId("share-link-form");
    await userEvent.type(
      within(form).getByTestId("share-link-label"),
      "Для комиссии",
    );
    await userEvent.click(screen.getByTestId("share-link-submit"));
    const created = await screen.findByTestId("share-link-created-url");
    expect(
      within(created).getByRole<HTMLInputElement>("textbox").value,
    ).toMatch(/\/s\/hsl_/);
  });

  it("гость открывает ссылку Редактора с именем и попадает в проект", async () => {
    activateServerScenario("registration_open");
    mount(<div />, "/s/hsl_demoEditor");
    expect(await screen.findByTestId("share-link-guest-name")).toBeTruthy();
    await userEvent.type(screen.getByTestId("share-link-guest-name"), "Борис");
    await userEvent.click(screen.getByTestId("share-link-open"));
    expect(await screen.findByTestId("landed")).toBeTruthy();
    await waitFor(() => {
      expect(getServerWorld().bootstrap.guest?.name).toBe("Борис");
    });
  });

  it("пароль: неверный показывает ошибку", async () => {
    activateServerScenario("registration_open");
    mount(<div />, "/s/hsl_demoPassword");
    await userEvent.type(
      await screen.findByTestId("share-link-password-input"),
      "wrong-pass",
    );
    await userEvent.click(screen.getByTestId("share-link-open"));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Неверный пароль",
    );
  });

  it("неизвестный токен: ссылка не действует", async () => {
    activateServerScenario("registration_open");
    mount(<div />, "/s/hsl_nothing");
    await waitFor(() => {
      expect(screen.getByTestId("share-link-page").dataset.state).toBe(
        "inactive",
      );
    });
  });
});
