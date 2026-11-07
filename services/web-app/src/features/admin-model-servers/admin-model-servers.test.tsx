import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
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
import { opsApi } from "@features/admin-ops/api/opsApi";
import { ensureAdminOpsLocales } from "@features/admin-ops/lib/locales";
import { modelServersApi } from "./api/modelServersApi";
import type { Capabilities, Estimate, ModelServer } from "./api/schemas";
import { ensureAdminModelServersLocales } from "./lib/locales";
import { ModelServersPage } from "./ui/ModelServersPage";

const caps = (patch: Partial<Capabilities> = {}): Capabilities => ({
  local_enabled: true,
  docker_available: true,
  hardware: {
    gpu_vendor: "none",
    gpu_name: null,
    vram_mb: null,
    total_ram_mb: 16384,
    cpu_count: 8,
    docker_gpu_supported: false,
    arch: "x86_64",
    disk_free_mb: 200000,
  },
  engines: [
    { engine: "ollama", image: "ollama/ollama", available: true, reasons: [] },
    {
      engine: "vllm",
      image: "vllm",
      available: false,
      reasons: ["engine_requires_gpu"],
    },
    {
      engine: "sglang",
      image: "sglang",
      available: false,
      reasons: ["engine_requires_gpu"],
    },
  ],
  ...patch,
});

const est = (patch: Partial<Estimate> = {}): Estimate => ({
  fit: "fits",
  params_b: 8,
  weights_mb: 4800,
  needed_mb: 6000,
  available_mb: 16384,
  memory_kind: "ram",
  disk_ok: true,
  reasons: [],
  ...patch,
});

const server = (patch: Partial<ModelServer> = {}): ModelServer => ({
  id: "ab12",
  engine: "ollama",
  model: "qwen3:8b",
  name: "Локальная Qwen",
  status: "running",
  endpoint: "http://hse-ms-ab12:11434",
  provider_id: "11111111-1111-1111-1111-111111111111",
  image: "ollama/ollama",
  steps: {
    container: "done",
    engine: "done",
    model: "done",
    provider: "done",
    verify: "done",
  },
  percent: 100,
  text: "",
  error: null,
  target: "local",
  host: "",
  exposure: "internal",
  manageable: true,
  ...patch,
});

const view = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <ModelServersPage />
      </QueryClientProvider>
    </I18nextProvider>,
  );

describe("страница серверов моделей", () => {
  beforeAll(async () => {
    // Radix Select в jsdom: нет указателя и прокрутки.
    Element.prototype.hasPointerCapture = () => false;
    Element.prototype.releasePointerCapture = () => undefined;
    Element.prototype.scrollIntoView = () => undefined;
    await ensureAdminModelServersLocales();
    await ensureAdminOpsLocales();
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    vi.spyOn(modelServersApi, "capabilities").mockResolvedValue(caps());
    vi.spyOn(modelServersApi, "list").mockResolvedValue([]);
    vi.spyOn(modelServersApi, "catalog").mockResolvedValue([
      { ref: "qwen3:8b", title: "Qwen3 8B", params_b: 8, quant: "q4" },
    ]);
    vi.spyOn(modelServersApi, "estimate").mockResolvedValue(est());
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает железо и причину, почему vLLM недоступен", async () => {
    view();
    expect(await screen.findByTestId("ms-hardware")).toBeInTheDocument();
    expect(screen.getByTestId("ms-engine-ollama")).toHaveTextContent(
      "подходит",
    );
    expect(screen.getByTestId("ms-engine-vllm")).toHaveTextContent(
      "нужна видеокарта NVIDIA",
    );
  });

  it("оценка до установки и запуск установки по имени модели", async () => {
    const install = vi
      .spyOn(modelServersApi, "install")
      .mockResolvedValue(server({ status: "installing" }));
    view();
    await userEvent.type(await screen.findByTestId("ms-model"), "qwen3:8b");
    expect(await screen.findByTestId("ms-estimate")).toHaveTextContent(
      "Поместится",
    );
    await userEvent.click(screen.getByTestId("ms-install-submit"));
    await waitFor(() => {
      expect(install).toHaveBeenCalledWith({
        engine: "ollama",
        model: "qwen3:8b",
        name: "",
        force: false,
      });
    });
  });

  it("не помещающаяся модель блокирует установку до подтверждения", async () => {
    vi.spyOn(modelServersApi, "estimate").mockResolvedValue(
      est({ fit: "too_large", reasons: ["memory_low"] }),
    );
    view();
    await userEvent.type(await screen.findByTestId("ms-model"), "huge-70b");
    expect(await screen.findByText("памяти не хватит")).toBeInTheDocument();
    expect(screen.getByTestId("ms-install-submit")).toBeDisabled();
    await userEvent.click(screen.getByTestId("ms-force"));
    expect(screen.getByTestId("ms-install-submit")).toBeEnabled();
  });

  it("код ошибки API превращается в понятный текст", async () => {
    const { ApiError } = await import("@shared/api");
    vi.spyOn(modelServersApi, "install").mockRejectedValue(
      new ApiError("x", "model_server_busy", 409),
    );
    view();
    await userEvent.type(await screen.findByTestId("ms-model"), "qwen3:8b");
    await userEvent.click(await screen.findByTestId("ms-install-submit"));
    expect(await screen.findByTestId("ms-install-error")).toHaveTextContent(
      "Уже идёт другая установка",
    );
  });

  it("ход установки по шагам и действия над работающим сервером", async () => {
    const list = vi.spyOn(modelServersApi, "list").mockResolvedValue([
      server({
        id: "i1",
        status: "installing",
        percent: 40,
        steps: {
          container: "done",
          engine: "done",
          model: "running",
          provider: "pending",
          verify: "pending",
        },
      }),
      server({ id: "r1" }),
    ]);
    const stop = vi
      .spyOn(modelServersApi, "stop")
      .mockResolvedValue(server({ id: "r1", status: "stopped" }));
    view();
    expect(await screen.findByTestId("ms-progress-i1")).toHaveTextContent(
      "Модель: идёт",
    );
    const card = await screen.findByTestId("ms-server-r1");
    await userEvent.click(card.querySelector("button") as HTMLElement);
    await waitFor(() => {
      expect(stop).toHaveBeenCalledWith("r1");
    });
    expect(list).toHaveBeenCalled();
  });

  it("журнал сервера открывается по кнопке", async () => {
    vi.spyOn(modelServersApi, "list").mockResolvedValue([server()]);
    vi.spyOn(modelServersApi, "logs").mockResolvedValue("строка журнала");
    view();
    await userEvent.click(await screen.findByTestId("ms-logs-ab12"));
    expect(await screen.findByTestId("ms-logtext-ab12")).toHaveTextContent(
      "строка журнала",
    );
  });

  it("при выключенной локальной установке форма скрыта", async () => {
    vi.spyOn(modelServersApi, "capabilities").mockResolvedValue(
      caps({ local_enabled: false }),
    );
    view();
    expect(await screen.findByTestId("ms-disabled")).toBeInTheDocument();
    // Форма остаётся для установки по SSH, но «на этой машине» выбрать нельзя.
    expect(await screen.findByTestId("ms-install")).toBeInTheDocument();
    expect(screen.getByTestId("ms-install-submit")).toHaveTextContent("по SSH");
  });

  it("токен Hugging Face: сохраняется, значение не показывается, можно удалить", async () => {
    const settings = vi
      .spyOn(modelServersApi, "settings")
      .mockResolvedValue({ hf_token_set: false });
    const save = vi
      .spyOn(modelServersApi, "saveHfToken")
      .mockResolvedValue({ hf_token_set: true });
    const clear = vi
      .spyOn(modelServersApi, "clearHfToken")
      .mockResolvedValue({ hf_token_set: false });
    view();
    const input = await screen.findByTestId("ms-hf-input");
    expect(input).toHaveAttribute("type", "password");
    expect(screen.getByTestId("ms-hf-state")).toHaveTextContent("Не задан");
    await userEvent.type(input, "hf_SECRET");
    await userEvent.click(screen.getByTestId("ms-hf-save"));
    await waitFor(() => {
      expect(save).toHaveBeenCalledWith("hf_SECRET");
    });
    expect(await screen.findByTestId("ms-hf-state")).toHaveTextContent(
      "Сохранён",
    );
    expect(screen.getByTestId("ms-hf-input")).toHaveValue("");
    expect(document.body.textContent).not.toContain("hf_SECRET");
    await userEvent.click(screen.getByTestId("ms-hf-clear"));
    await waitFor(() => {
      expect(clear).toHaveBeenCalled();
    });
    expect(settings).toHaveBeenCalled();
  });

  it("по SSH: наружу только с подтверждением, Ollama наружу нельзя, установка уходит в общий SSH-слой", async () => {
    vi.spyOn(modelServersApi, "capabilities").mockResolvedValue(
      caps({ docker_available: false }),
    );
    vi.spyOn(opsApi, "sshCapability").mockResolvedValue({
      enabled: true,
      can_save_credentials: true,
    });
    vi.spyOn(opsApi, "sshCredentials").mockResolvedValue([]);
    const probe = vi.spyOn(opsApi, "sshProbe").mockResolvedValue({
      session_id: "s1",
      host_key: { key_type: "ssh-ed25519", fingerprint: "SHA256:abc" },
      expires_in_s: 900,
    });
    vi.spyOn(opsApi, "sshConfirm").mockResolvedValue({
      session_id: "s1",
      system: {
        os: "linux",
        arch: "x86_64",
        distro: "ubuntu",
        has_docker: true,
        docker_usable: true,
        has_systemd: true,
        is_root: true,
      },
      plan: [{ key: "docker", action: "skip" }],
    });
    const install = vi.spyOn(opsApi, "sshInstall").mockResolvedValue({
      id: "j1",
      target: "ssh",
      name: "vllm Qwen/Qwen3-4B",
      state: "running",
      steps: [],
      error_code: null,
      error_detail: "",
      created_at: "2026-11-07T10:00:00Z",
    });
    vi.spyOn(opsApi, "sshCancel").mockResolvedValue(undefined);
    view();
    // Локально недоступно (нет Docker), значит выбрано «по SSH»; движок vLLM.
    await userEvent.click(await screen.findByLabelText("Движок"));
    await userEvent.click(await screen.findByRole("option", { name: "vLLM" }));
    await userEvent.click(await screen.findByLabelText("Доступ к серверу"));
    await userEvent.click(
      await screen.findByRole("option", { name: /Из сети/ }),
    );
    await userEvent.type(
      await screen.findByTestId("ms-model"),
      "Qwen/Qwen3-4B",
    );
    expect(screen.getByTestId("ms-install-submit")).toBeDisabled();
    await userEvent.click(screen.getByTestId("ms-ack-public"));
    expect(screen.getByTestId("ms-install-submit")).toBeEnabled();
    await userEvent.click(screen.getByTestId("ms-install-submit"));

    await userEvent.type(
      await screen.findByTestId("ssh-host"),
      "srv.example.org",
    );
    await userEvent.type(screen.getByTestId("ssh-username"), "deploy");
    await userEvent.type(screen.getByTestId("ssh-password"), "s3cret");
    expect(screen.queryByTestId("ssh-runner-name")).toBeNull();
    await userEvent.click(screen.getByTestId("ssh-probe-submit"));
    await waitFor(() => {
      expect(probe).toHaveBeenCalled();
    });
    await userEvent.click(await screen.findByTestId("ssh-confirm"));
    expect(await screen.findByTestId("ssh-model-summary")).toHaveTextContent(
      "Qwen/Qwen3-4B",
    );
    await userEvent.click(screen.getByTestId("ssh-install"));
    await waitFor(() => {
      expect(install).toHaveBeenCalled();
    });
    expect(install.mock.calls[0]?.[1].model_server).toEqual({
      engine: "vllm",
      model: "Qwen/Qwen3-4B",
      name: "",
      exposure: "public",
      acknowledge_public: true,
      force: false,
    });
  }, 30_000);

  it("сервер по SSH без сохранённого доступа: подсказка и нет кнопок запуска и остановки", async () => {
    vi.spyOn(modelServersApi, "list").mockResolvedValue([
      server({
        id: "s1",
        target: "ssh",
        host: "srv.example.org",
        manageable: false,
        exposure: "localhost",
      }),
    ]);
    view();
    expect(await screen.findByTestId("ms-unmanaged-s1")).toBeInTheDocument();
    expect(screen.getByTestId("ms-target-s1")).toHaveTextContent(
      "srv.example.org",
    );
    const card = screen.getByTestId("ms-server-s1");
    expect(
      within(card).queryByRole("button", { name: "Остановить" }),
    ).toBeNull();
  });

  it("английский словарь содержит те же ключи", async () => {
    await i18n.changeLanguage("en");
    vi.spyOn(modelServersApi, "capabilities").mockResolvedValue(
      caps({ docker_available: false }),
    );
    view();
    expect(await screen.findByTestId("ms-no-docker")).toHaveTextContent(
      "cannot see Docker",
    );
    await i18n.changeLanguage("ru");
  });
});
