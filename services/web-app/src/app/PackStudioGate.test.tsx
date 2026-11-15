import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { packStudioApi } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { PackStudioGate } from "./PackStudioGate";

// Считаем загрузки чанка Студии шаблонов: без возможности модуль не вычисляется.
const loaded = vi.hoisted(() => ({ count: 0 }));
vi.mock("@pages/PackStudioPage", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "@pages/PackStudioPage",
  );
  loaded.count += 1;
  return actual;
});
vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));

const bootstrap = (pack_studio: boolean): Bootstrap => ({
  ...LOCAL_BOOTSTRAP,
  capabilities: { ...LOCAL_BOOTSTRAP.capabilities, pack_studio },
});

const mount = (data: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), data);
  const router = createMemoryRouter(
    [{ path: "/pack-studio/*", element: <PackStudioGate /> }],
    { initialEntries: ["/pack-studio"] },
  );
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <RouterProvider router={router} />
      </I18nextProvider>
    </QueryClientProvider>,
  );
};

describe("PackStudioGate", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("без capabilities.pack_studio страница «не найдено» и чанк не грузится", async () => {
    mount(bootstrap(false));
    expect(await screen.findByText("404")).toBeInTheDocument();
    expect(loaded.count).toBe(0);
  });

  it("с возможностью: словарь и приложение, список пространств", async () => {
    vi.spyOn(packStudioApi, "workspaces").mockResolvedValue([]);
    mount(bootstrap(true));
    expect(
      await screen.findByTestId("ws-empty", undefined, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Студия шаблонов" }),
    ).toBeInTheDocument();
    expect(loaded.count).toBe(1);
  });
});
