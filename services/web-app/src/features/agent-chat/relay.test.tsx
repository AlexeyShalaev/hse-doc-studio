import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  defaultProvider,
  orderProviders,
  type AIProvider,
} from "@entities/ai-provider";
import { reduceEvent, type AgentStreamState } from "./lib/useAgentRunStream";
import { ModelPicker } from "./ui/ModelPicker";
import { RelayErrorBlock } from "./ui/RelayErrorBlock";

const provider = (extra: Partial<AIProvider>): AIProvider => ({
  id: "p",
  name: "p",
  type: "openai",
  base_url: "",
  models: ["m"],
  has_api_key: true,
  created_at: "2026-10-01T00:00:00Z",
  ssl_verify: true,
  connect_timeout_s: 10,
  request_timeout_s: 60,
  ...extra,
});

describe("порядок провайдеров по умолчанию", () => {
  it("свои, затем организации, затем установки; неготовый раннер пропускается", () => {
    const instance = provider({ id: "i", source: "instance", shared: true });
    const relay = provider({
      id: "r",
      type: "runner",
      source: "own",
      created_at: "2026-09-01T00:00:00Z",
      relay: {
        runner_id: "x",
        runner_name: "MacBook",
        endpoint: "ollama",
        flavor: "ollama",
        state: "runner_offline",
      },
    });
    const own = provider({ id: "o", source: "own" });
    expect(orderProviders([instance, own, relay]).map((p) => p.id)).toEqual([
      "r",
      "o",
      "i",
    ]);
    expect(defaultProvider([instance, own, relay])?.id).toBe("o");
    expect(defaultProvider([instance])?.id).toBe("i");
  });
});

describe("ИИ через раннер в чате", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("код ошибки рана сохраняется из done и error", () => {
    const base = {
      status: "running",
      liveText: "",
      approvals: [],
      questions: [],
      usage: null,
      doneStatus: null,
      error: null,
      errorCode: null,
      debug: [],
      lastEventAt: null,
    } satisfies AgentStreamState;
    const done = reduceEvent(base, "done", {
      status: "failed",
      message: "Раннер не ответил",
      code: "relay_unavailable",
    });
    expect(done.errorCode).toBe("relay_unavailable");
    expect(reduceEvent(base, "error", { code: "relay_busy" }).errorCode).toBe(
      "relay_busy",
    );
  });

  it("блок ошибки называет раннер и открывает выбор модели", async () => {
    const onPick = vi.fn();
    render(
      <RelayErrorBlock
        code="relay_unavailable"
        runnerName="MacBook Анны"
        onPickModel={onPick}
      />,
    );
    expect(screen.getByTestId("chat-relay-error")).toHaveTextContent(
      "Раннер «MacBook Анны» не ответил. Запустите его или выберите другую модель.",
    );
    await userEvent.click(screen.getByTestId("chat-relay-error-pick"));
    expect(onPick).toHaveBeenCalledOnce();
    cleanup();
    render(
      <RelayErrorBlock
        code="relay_busy"
        runnerName={null}
        onPickModel={onPick}
      />,
    );
    expect(screen.getByTestId("chat-relay-error")).toHaveTextContent(
      "Слишком много запросов к раннеру одновременно",
    );
  });

  it("выбор модели: группы по источнику, неготовые недоступны", async () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <ModelPicker
        groups={[
          {
            providerId: "r",
            providerName: "Ollama на ноутбуке",
            models: ["qwen2.5:7b"],
            source: "own",
            unavailable: "раннер не в сети",
          },
          {
            providerId: "i",
            providerName: "Общий Claude",
            models: ["claude-sonnet-4-5"],
            source: "instance",
            unavailable: null,
          },
        ]}
        selectedProviderId=""
        selectedModel=""
        onSelect={onSelect}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Модель/ }));
    expect(screen.getByTestId("model-picker-default-order")).toHaveTextContent(
      "По умолчанию: мои, затем организации, затем установки",
    );
    expect(screen.getByTestId("model-picker-group-own")).toBeInTheDocument();
    expect(screen.queryByTestId("model-picker-group-org")).toBeNull();
    const offline = screen.getByRole("button", { name: /qwen2\.5:7b/ });
    expect(offline).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", { name: /claude-sonnet-4-5/ }),
    );
    expect(onSelect).toHaveBeenCalledWith("i", "claude-sonnet-4-5");
    // Кнопка «Выбрать модель» у ошибки открывает список снаружи.
    rerender(
      <ModelPicker
        groups={[
          {
            providerId: "i",
            providerName: "Общий Claude",
            models: ["claude-sonnet-4-5"],
            source: "instance",
          },
        ]}
        selectedProviderId=""
        selectedModel=""
        openRequest={1}
        onSelect={onSelect}
      />,
    );
    expect(
      await screen.findByTestId("model-picker-group-instance"),
    ).toBeInTheDocument();
  });
});
