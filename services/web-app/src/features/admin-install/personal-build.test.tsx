import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import { AdminBuildSettingsSchema, BootstrapSchema } from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import {
  serverAdminDemoRoutes,
  serverDemoRoutes,
} from "@/app/demo/server/routes";
import { InstancePage } from "./index";

const mount = (node: ReactNode) =>
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
        <MemoryRouter>{node}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const makeCall =
  (routes: typeof serverAdminDemoRoutes) =>
  async (method: DemoRequest["method"], path: string, body?: unknown) => {
    const found = createDemoRouter(routes).match(method, path);
    if (!found) throw new Error(`no demo route ${method} ${path}`);
    return found.handler({
      method,
      path,
      params: found.params,
      query: {},
      body,
      forward: () => Promise.reject(new Error("forward")),
    });
  };
const call = makeCall(serverAdminDemoRoutes);
const callUser = makeCall(serverDemoRoutes);

describe("настройки сборки: личные раннеры", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_personal_runners");
  });
  afterEach(cleanup);

  it("демо отдаёт три поля и ключи runners.*", async () => {
    const build = AdminBuildSettingsSchema.parse(
      (await call("GET", "/settings/build")).data,
    );
    expect(build).toMatchObject({
      personal_runners_enabled: true,
      personal_runner_wait_s: 5,
      personal_runners_max_per_user: 5,
    });
    expect(Object.keys(build.fields)).toEqual(
      expect.arrayContaining([
        "runners.personal_enabled",
        "runners.personal_wait_s",
        "runners.personal_max_per_user",
      ]),
    );
  });

  it("выключение просит подтверждения и меняет возможности людей", async () => {
    const user = userEvent.setup();
    mount(<InstancePage />);
    await user.click(
      await screen.findByTestId("admin-personal-runners-toggle"),
    );
    await user.click(screen.getByTestId("save-bar-save"));
    expect(
      await screen.findByText(/ИИ через раннеры перестанет работать/),
    ).toBeVisible();
    await user.click(screen.getByTestId("admin-personal-off-confirm"));
    await waitFor(() => {
      expect(screen.queryByTestId("save-bar")).toBeNull();
    });
    const build = AdminBuildSettingsSchema.parse(
      (await call("GET", "/settings/build")).data,
    );
    expect(build.personal_runners_enabled).toBe(false);
    const boot = BootstrapSchema.parse(
      (await callUser("GET", "/session/bootstrap")).data,
    );
    expect(boot.capabilities.personal_runners).toBe(false);
  });

  it("окно ожидания вне диапазона не сохраняется", async () => {
    const user = userEvent.setup();
    mount(<InstancePage />);
    const wait = await screen.findByTestId("admin-personal-wait-s");
    await user.clear(wait);
    await user.type(wait, "99");
    expect(screen.getByText(/Целое число от 0 до 60/)).toBeVisible();
    expect(screen.getByTestId("save-bar-save")).toBeDisabled();
  });

  it("значение из окружения закрыто", async () => {
    activateServerScenario("install_env_locked");
    mount(<InstancePage />);
    expect(
      await screen.findByTestId("build-personal-enabled-locked"),
    ).toBeVisible();
    expect(screen.getByTestId("admin-personal-runners-toggle")).toBeDisabled();
  });
});
