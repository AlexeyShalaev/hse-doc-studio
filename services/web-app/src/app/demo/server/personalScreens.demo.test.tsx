import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import { MyRunnersSection } from "@features/my-runners";
import { AIProviderEditorModal } from "@features/manage-ai-provider";
import { AIProviderSchema } from "@entities/ai-provider";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import { z } from "zod";
import { serverDemoRoutes } from "./routes";
import { RunnerPairPage } from "@pages/RunnerPairPage";
import { installServerDemo } from "../index";
import { activateServerScenario } from "./index";

// «Мои раннеры» поверх демо-транспорта: те же запросы, что уйдут настоящему
// бэкенду, и ответы, проходящие схемы эталонов.

const Where = () => <span data-testid="where">{useLocation().search}</span>;

const mountLive = () =>
  render(
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
      <MemoryRouter initialEntries={["/settings/runners"]}>
        <Routes>
          <Route path="/settings/runners" element={<MyRunnersSection />} />
          <Route path="/settings/runners/pair" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

// Кнопка подключения доступна, когда bootstrap сказал, что личные раннеры разрешены.
const openConnect = async (user: ReturnType<typeof userEvent.setup>) => {
  const button = await screen.findByTestId("my-runner-connect");
  await waitFor(() => {
    expect(button).toBeEnabled();
  });
  await user.click(button);
};

describe("«Мои раннеры» на демо-мире", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("runners_ready");
  });
  afterEach(cleanup);

  it("пауза, переименование и отзыв по имени", async () => {
    const user = userEvent.setup();
    mountLive();
    const id = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b";
    await user.click(await screen.findByTestId(`my-runner-actions-${id}`));
    await user.click(await screen.findByTestId(`my-runner-pause-${id}`));
    await waitFor(() => {
      expect(screen.getByTestId(`my-runner-status-${id}`)).toHaveAttribute(
        "data-status",
        "paused",
      );
    });

    await user.click(screen.getByTestId(`my-runner-actions-${id}`));
    await user.click(await screen.findByTestId(`my-runner-rename-${id}`));
    const input = await screen.findByTestId("my-runner-rename-input");
    await user.clear(input);
    await user.type(input, "Мак");
    await user.click(screen.getByTestId("my-runner-rename-save"));
    await waitFor(() => {
      expect(screen.getByTestId(`my-runner-row-${id}`)).toHaveTextContent(
        "Мак",
      );
    });

    await user.click(screen.getByTestId(`my-runner-actions-${id}`));
    await user.click(await screen.findByTestId(`my-runner-revoke-${id}`));
    await user.type(await screen.findByRole("textbox"), "Мак");
    await user.click(screen.getByRole("button", { name: "Отозвать" }));
    await waitFor(() => {
      expect(screen.queryByTestId(`my-runner-row-${id}`)).toBeNull();
    });
  });

  it("смена токена консольного раннера показывает новый токен один раз", async () => {
    const user = userEvent.setup();
    mountLive();
    const id = "5e6f7a8b9c0d41e2f3a4b5c6d7e8f9a0";
    await user.click(await screen.findByTestId(`my-runner-actions-${id}`));
    await user.click(await screen.findByTestId(`my-runner-rotate-${id}`));
    await user.click(
      await screen.findByTestId("my-runner-rotate-dialog-confirm"),
    );
    const rotated = await screen.findByTestId("my-runner-rotated");
    expect(rotated).toHaveTextContent("HSE_RUNNER__RUNNER_TOKEN=hsrn_");
  });

  it("код из Студии ведёт на страницу подтверждения", async () => {
    const user = userEvent.setup();
    mountLive();
    await openConnect(user);
    await user.type(
      await screen.findByTestId("runner-pair-code-input"),
      "bcdf2345",
    );
    await user.click(screen.getByTestId("runner-pair-code-continue"));
    expect(await screen.findByTestId("where")).toHaveTextContent(
      "?code=BCDF-2345",
    );
  });

  it("создание токена: секрет и обе команды", async () => {
    const user = userEvent.setup();
    mountLive();
    await openConnect(user);
    await user.click(screen.getByTestId("runner-connect-tab-server"));
    await user.type(screen.getByTestId("runner-token-label"), "Лаборатория");
    await user.click(screen.getByTestId("runner-token-create-submit"));
    expect(await screen.findByTestId("runner-token-command")).toHaveTextContent(
      "hse-doc-studio runner",
    );
    await user.click(screen.getByTestId("runner-token-how-docker"));
    expect(screen.getByTestId("runner-token-docker-command")).toHaveTextContent(
      "docker run",
    );
  });
});

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));

const mountPair = (path: string) =>
  render(
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
          <Route path="/settings/runners/pair" element={<RunnerPairPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("подтверждение сопряжения на демо-мире", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("runners_ready");
  });
  afterEach(cleanup);

  it("код из адреса: подтверждение подключает устройство", async () => {
    const user = userEvent.setup();
    mountPair("/settings/runners/pair?code=bcdf-2345");
    await user.click(await screen.findByTestId("runner-pair-approve"));
    expect(await screen.findByTestId("runner-pair-result")).toHaveAttribute(
      "data-state",
      "approved",
    );
  });

  it.each([
    ["XKCD-7777", "expired"],
    ["QRST-2468", "used"],
    ["ZZZZ-2222", "invalid"],
    ["nonsense", "invalid"],
  ])("код %s даёт итог %s", async (code, result) => {
    mountPair(`/settings/runners/pair?code=${code}`);
    expect(await screen.findByTestId("runner-pair-result")).toHaveAttribute(
      "data-state",
      result,
    );
  });

  it("предел раннеров и отказ", async () => {
    const user = userEvent.setup();
    mountPair("/settings/runners/pair?code=LMNP-6789");
    await user.click(await screen.findByTestId("runner-pair-approve"));
    expect(await screen.findByTestId("runner-pair-result")).toHaveAttribute(
      "data-state",
      "limit",
    );
    cleanup();
    mountPair("/settings/runners/pair?code=BCDF-2345");
    await user.click(await screen.findByTestId("runner-pair-deny"));
    expect(await screen.findByTestId("runner-pair-result")).toHaveAttribute(
      "data-state",
      "denied",
    );
  });
});

const userRouter = createDemoRouter(serverDemoRoutes);
const callUser = async (
  method: DemoRequest["method"],
  path: string,
  body?: unknown,
) => {
  const found = userRouter.match(method, path);
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

describe("ИИ через свой раннер на демо-мире", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("runners_ready");
  });
  afterEach(cleanup);

  it("список: свои впереди, у провайдера через раннер состояние и раннер", async () => {
    const list = z
      .array(AIProviderSchema)
      .parse((await callUser("GET", "/ai-providers")).data);
    expect(list[0]?.source).toBe("own");
    const relay = list.find((p) => p.type === "runner");
    expect(relay?.relay).toMatchObject({
      runner_name: "MacBook Анны",
      endpoint: "ollama",
      state: "ready",
    });
    expect(list.filter((p) => p.source === "instance").length).toBe(2);
  });

  it("раннер не в сети: состояние runner_offline и 503 на модели", async () => {
    activateServerScenario("runners_offline");
    const list = z
      .array(AIProviderSchema)
      .parse((await callUser("GET", "/ai-providers")).data);
    const relay = list.find((p) => p.type === "runner");
    expect(relay?.relay?.state).toBe("runner_offline");
    const models = await callUser(
      "GET",
      `/ai-providers/${relay?.id ?? ""}/models`,
    );
    expect(models.status).toBe(503);
    expect((models.data as { code: string }).code).toBe("relay_unavailable");
  });

  it("провайдер на чужой раннер или без адреса: 422", async () => {
    const base = {
      name: "x",
      type: "runner",
      api_key: "",
      base_url: "",
      models: [],
      ssl_verify: true,
      connect_timeout_s: 10,
      request_timeout_s: 120,
    };
    const foreign = await callUser("POST", "/ai-providers", {
      ...base,
      runner_id: "6a7b8c9d0e1f42a3b4c5d6e7f8a9b0c1",
      runner_endpoint: "ollama",
    });
    expect((foreign.data as { code: string }).code).toBe(
      "ai_provider_runner_invalid",
    );
    const created = await callUser("POST", "/ai-providers", {
      ...base,
      runner_id: "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b",
      runner_endpoint: "ollama",
    });
    expect(created.status).toBe(201);
    expect(AIProviderSchema.parse(created.data).relay?.state).toBe("ready");
  });

  it("окно добавления: вид «Через мой раннер», без раннеров ведёт к подключению", async () => {
    activateServerScenario("runners_none");
    const user = userEvent.setup();
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <AIProviderEditorModal isOpen onClose={() => undefined} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(await screen.findByTestId("ai-provider-kind-runner"));
    expect(
      await screen.findByTestId("ai-provider-no-runners"),
    ).toHaveTextContent("Сначала подключите раннер.");
  });
});
