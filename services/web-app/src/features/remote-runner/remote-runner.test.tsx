import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
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
import type { AIProvider } from "@entities/ai-provider";
import type { RemoteRunnerStatus } from "@entities/runner";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { cloudCandidates, isLocalNetworkUrl } from "./lib/candidates";
import { RemoteRunnerSection } from "./ui/RemoteRunnerSection";
import {
  RemoteRunnerView,
  type RemoteRunnerViewProps,
} from "./ui/RemoteRunnerView";

const ONLINE: RemoteRunnerStatus = {
  enabled: true,
  server_url: "https://studio.example.org",
  paired: true,
  runner_id: "r",
  runner_name: "MacBook Анны",
  state: "online",
  detail_code: null,
  running_jobs: 0,
  concurrency: 1,
  yield_to_local: true,
  docker: "ok",
  tex_image: "ready",
  ai_endpoints: [],
  pairing: null,
};
const noop = () => undefined;
const mount = (extra: Partial<RemoteRunnerViewProps>) =>
  render(
    <MemoryRouter>
      <RemoteRunnerView
        status={ONLINE}
        candidates={[
          {
            providerId: "o",
            name: "Ollama",
            flavor: "ollama",
            url: "http://localhost:11434/v1",
            defaultName: "ollama",
          },
        ]}
        now={Date.parse("2026-10-30T09:42:00Z")}
        onToggle={noop}
        onPair={noop}
        onToken={noop}
        onCancelPairing={noop}
        onUnpair={noop}
        onConcurrency={noop}
        onYield={noop}
        onModels={noop}
        {...extra}
      />
    </MemoryRouter>,
  );

const provider = (extra: Partial<AIProvider>): AIProvider => ({
  id: "p",
  name: "p",
  type: "openai_compat",
  base_url: "",
  models: [],
  has_api_key: false,
  created_at: "2026-10-01T00:00:00Z",
  ssl_verify: true,
  connect_timeout_s: 10,
  request_timeout_s: 60,
  ...extra,
});

describe("облачные сборки: модели для облака", () => {
  it("открыть облаку можно Ollama и адреса в своей сети", () => {
    expect(isLocalNetworkUrl("http://192.168.1.20:1234/v1")).toBe(true);
    expect(isLocalNetworkUrl("http://gpu.lan:8000/v1")).toBe(true);
    expect(isLocalNetworkUrl("https://api.openai.com/v1")).toBe(false);
    const list = cloudCandidates([
      provider({
        id: "a",
        type: "ollama",
        name: "Ollama",
        base_url: "http://localhost:11434/v1",
      }),
      provider({
        id: "b",
        name: "LM Studio",
        base_url: "http://192.168.1.20:1234/v1",
      }),
      provider({
        id: "c",
        name: "Облако",
        base_url: "https://llm.example.com/v1",
      }),
      provider({ id: "d", type: "claude", name: "Claude" }),
    ]);
    expect(list.map((c) => [c.providerId, c.defaultName, c.flavor])).toEqual([
      ["a", "ollama", "ollama"],
      ["b", "lm-studio", "openai"],
    ]);
  });
});

describe("облачные сборки: вид", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it.each([
    ["connecting", "Подключаемся…"],
    ["online", "В сети: берёт ваши облачные сборки"],
    ["paused", "На паузе (включите на сайте)"],
    ["offline", "Сервер недоступен, повторяем…"],
    ["disabled", "Администратор сервера выключил личные раннеры."],
  ] as const)("состояние %s", (state, text) => {
    mount({ status: { ...ONLINE, state } });
    const line = screen.getByTestId("remote-runner-state");
    expect(line).toHaveAttribute("data-state", state);
    expect(line).toHaveTextContent(text);
  });

  it("отозван: состояние и форма подключения заново", () => {
    mount({ status: { ...ONLINE, state: "revoked", paired: false } });
    expect(screen.getByTestId("remote-runner-state")).toHaveTextContent(
      "Раннер отозван на сервере. Подключите заново.",
    );
    expect(screen.getByTestId("remote-runner-pair")).toBeInTheDocument();
  });

  it("ждём код: крупный код, ссылка подтверждения и отсчёт", () => {
    mount({
      status: {
        ...ONLINE,
        paired: false,
        state: "pairing",
        pairing: {
          user_code: "BCDF-2345",
          verification_uri_complete:
            "https://studio.example.org/settings/runners/pair?code=BCDF-2345",
          expires_at: "2026-10-30T09:50:00Z",
        },
      },
    });
    expect(screen.getByTestId("remote-runner-user-code")).toHaveTextContent(
      "BCDF-2345",
    );
    expect(
      screen.getByTestId("remote-runner-open-verification"),
    ).toHaveAttribute(
      "href",
      "https://studio.example.org/settings/runners/pair?code=BCDF-2345",
    );
    expect(
      screen.getByTestId("remote-runner-code-countdown"),
    ).toHaveTextContent("8:00");
  });

  it("подключение: адрес http не принимается, токен проверяется", async () => {
    const onPair = vi.fn();
    const onToken = vi.fn();
    mount({
      status: { ...ONLINE, paired: false, state: "unpaired", server_url: null },
      onPair,
      onToken,
    });
    await userEvent.type(
      screen.getByTestId("remote-runner-server-url"),
      "http://studio.example.org",
    );
    await userEvent.click(screen.getByTestId("remote-runner-pair"));
    expect(onPair).not.toHaveBeenCalled();
    expect(screen.getByText(/http только для localhost/)).toBeInTheDocument();
    await userEvent.clear(screen.getByTestId("remote-runner-server-url"));
    await userEvent.type(
      screen.getByTestId("remote-runner-server-url"),
      "https://studio.example.org",
    );
    await userEvent.click(screen.getByTestId("remote-runner-have-token"));
    // Токен секретный: поле скрывает ввод, как ключ ИИ-провайдера.
    expect(screen.getByTestId("remote-runner-token-input")).toHaveAttribute(
      "type",
      "password",
    );
    await userEvent.type(
      screen.getByTestId("remote-runner-token-input"),
      "abc",
    );
    await userEvent.click(screen.getByTestId("remote-runner-use-token"));
    expect(onToken).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByTestId("remote-runner-token-input"));
    await userEvent.type(
      screen.getByTestId("remote-runner-token-input"),
      "hsrt_x",
    );
    await userEvent.click(screen.getByTestId("remote-runner-use-token"));
    expect(onToken).toHaveBeenCalledWith(
      "https://studio.example.org",
      "hsrt_x",
    );
  });

  it("проверки: нет Docker", () => {
    mount({ status: { ...ONLINE, docker: "missing", tex_image: "missing" } });
    expect(screen.getByText(/Docker недоступен/)).toBeInTheDocument();
  });

  it("модель открывается облаку флажком", async () => {
    const onModels = vi.fn();
    mount({ onModels });
    await userEvent.click(screen.getByRole("checkbox", { name: /Ollama/ }));
    expect(onModels).toHaveBeenCalledWith([
      { provider_id: "o", name: "ollama" },
    ]);
  });
});

describe("облачные сборки на демо-мире", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("local_remote_off");
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("включение, подключение кодом и отключение", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <RemoteRunnerSection />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(await screen.findByTestId("remote-runner-toggle"));
    await user.type(
      await screen.findByTestId("remote-runner-server-url"),
      "https://studio.example.org",
    );
    await user.click(screen.getByTestId("remote-runner-pair"));
    expect(
      await screen.findByTestId("remote-runner-user-code"),
    ).toHaveTextContent("BCDF-2345");
    await user.click(screen.getByTestId("remote-runner-cancel-pairing"));
    await waitFor(() => {
      expect(screen.getByTestId("remote-runner-state")).toHaveAttribute(
        "data-state",
        "unpaired",
      );
    });
    await user.click(screen.getByTestId("remote-runner-have-token"));
    await user.type(
      screen.getByTestId("remote-runner-token-input"),
      "hsrt_abc",
    );
    await user.click(screen.getByTestId("remote-runner-use-token"));
    await waitFor(() => {
      expect(screen.getByTestId("remote-runner-state")).toHaveAttribute(
        "data-state",
        "online",
      );
    });
    await user.click(screen.getByTestId("remote-runner-unpair"));
    await user.click(await screen.findByTestId("remote-runner-unpair-confirm"));
    await waitFor(() => {
      expect(screen.getByTestId("remote-runner-toggle")).toHaveAttribute(
        "aria-checked",
        "false",
      );
    });
  });
});
