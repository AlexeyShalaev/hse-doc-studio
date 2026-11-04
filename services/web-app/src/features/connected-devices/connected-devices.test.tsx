import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  NOW,
  makeDevice,
  makeEndpoint,
  makeLink,
  makeServer,
  minutesBefore,
} from "@entities/connected-device/testing";
import type { ProjectStudios } from "@entities/connected-device";
import { cloudSummary, localSummary } from "./model/summary";
import { CloudStudiosPanel } from "./ui/CloudStudiosPanel";
import { LocalLinkPanel } from "./ui/LocalLinkPanel";
import { StudioPresence } from "./ui/StudioPresence";
import { StudioProviderBanner } from "./ui/StudioProviderBanner";

const api = vi.hoisted(() => ({
  project: vi.fn(),
  account: vi.fn(),
  link: vi.fn(),
  create: vi.fn(),
  fetchModels: vi.fn(),
  update: vi.fn(),
  mode: { value: "server" },
}));

vi.mock("@entities/connected-device/api/deviceApi", () => ({
  deviceApi: {
    project: api.project,
    account: api.account,
    forget: vi.fn(),
  },
  studioLinkApi: { link: api.link, device: vi.fn(), rename: vi.fn() },
}));

vi.mock("@entities/ai-provider", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/ai-provider")),
  aiProviderApi: {
    create: api.create,
    fetchModels: api.fetchModels,
    update: api.update,
  },
}));

vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useBootstrap: () => ({ data: { mode: api.mode.value } }),
}));

const t = i18n.getFixedT("ru", "devices");

const studios = (over: Partial<ProjectStudios> = {}): ProjectStudios => ({
  online_window_s: 180,
  mine: [makeDevice()],
  others: [],
  ...over,
});

const wrap = (node: React.ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
};

beforeEach(() => {
  vi.setSystemTime(NOW);
  api.mode.value = "server";
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("плашка облака", () => {
  it("своя Студия онлайн: имя в подписи", () => {
    expect(cloudSummary(t, studios())).toMatchObject({
      label: "Студия в сети: MacBook Анны",
      online: true,
    });
  });

  it("Студия не в сети", () => {
    const off = makeDevice({
      presence: "offline",
      last_seen_at: minutesBefore(30),
    });
    expect(cloudSummary(t, studios({ mine: [off] }))).toMatchObject({
      label: "Студия не в сети: MacBook Анны",
      tone: "quiet",
      online: false,
    });
  });

  it("у чужого участника только «работает локально», без имени машины", () => {
    const summary = cloudSummary(
      t,
      studios({ mine: [], others: [{ user_id: "u2", name: "Борис Смирнов" }] }),
    );
    expect(summary?.label).toBe("Работает локально: Борис Смирнов");
  });

  it("показывать нечего: плашки нет", () => {
    expect(cloudSummary(t, studios({ mine: [], others: [] }))).toBeNull();
    expect(cloudSummary(t, undefined)).toBeNull();
  });
});

describe("плашка локальной Студии", () => {
  it("облако видит Студию", () => {
    expect(localSummary(t, makeLink())?.label).toBe("Облако в сети");
  });

  it("проект не подключён к облаку: плашки нет", () => {
    expect(localSummary(t, makeLink({ project: null }))).toBeNull();
  });

  it("вход истёк, отозван, сервер не отвечает, сигнала пока нет", () => {
    const of = (over: Parameters<typeof makeServer>[0]) =>
      localSummary(t, makeLink({ servers: [makeServer(over)] }))?.label;
    expect(of({ state: "expired" })).toBe("Вход на сервер истёк");
    expect(of({ state: "revoked" })).toBe("Вход на сервер отозван");
    expect(of({ state: "unreachable" })).toBe("Нет связи с сервером");
    expect(of({ cloud: null, cloud_error: "presence_unsupported" })).toBe(
      "Нет связи с сервером",
    );
    expect(
      of({ cloud: { online_window_s: 180, device: null, others: [] } }),
    ).toBe("Облако не видит Студию");
  });
});

describe("панель облака", () => {
  it("свои Студии подробно, чужие одной строкой без деталей", () => {
    render(
      <CloudStudiosPanel
        studios={studios({
          others: [{ user_id: "u2", name: "Борис Смирнов" }],
        })}
        now={NOW}
        onAddProvider={vi.fn()}
      />,
    );
    const mine = screen.getAllByTestId("device-card");
    expect(mine).toHaveLength(1);
    expect(within(mine[0]!).getByTestId("device-name")).toHaveTextContent(
      "MacBook Анны",
    );
    const other = screen.getByTestId("studio-other");
    expect(other).toHaveTextContent("Борис Смирнов работает локально");
    // Чужому участнику нет карточки: ни версии, ни раннера, ни моделей.
    expect(within(other).queryByText(/0\.5\.0/)).toBeNull();
    expect(screen.getAllByTestId("device-runner")).toHaveLength(1);
  });

  it("карточка: активность, синхронизация, выгрузка PDF, раннер и модели", () => {
    render(
      <CloudStudiosPanel
        studios={studios({
          mine: [
            makeDevice({
              activity: "building",
              project: {
                sync: "ahead",
                ahead: 2,
                behind: 0,
                last_sync_at: minutesBefore(4),
                auto_sync: false,
                pdf: {
                  doc_id: "tz",
                  at: minutesBefore(12),
                  ok: false,
                  code: "pdf_forbidden",
                },
              },
              runner: {
                id: "r",
                name: "MacBook Анны",
                state: "online",
                tags: ["tex"],
                concurrency: 1,
                running_jobs: 1,
                busy: true,
              },
            }),
          ],
        })}
        now={NOW}
        onAddProvider={vi.fn()}
      />,
    );
    expect(screen.getByTestId("device-activity")).toHaveTextContent("собирает");
    const project = screen.getByTestId("device-project");
    expect(project).toHaveTextContent("есть неотправленные изменения");
    expect(project).toHaveTextContent("впереди на 2 коммита");
    expect(project).toHaveTextContent("последняя синхронизация 4 минуты назад");
    expect(project).toHaveTextContent("автосинхронизация выключена");
    expect(screen.getByTestId("device-pdf")).toHaveTextContent(
      "выгрузка PDF не удалась",
    );
    expect(screen.getByTestId("device-runner")).toHaveTextContent(
      "занят: 1 из 1",
    );
    expect(screen.getByTestId("device-endpoint-ollama")).toHaveTextContent(
      "qwen3:4b-instruct",
    );
  });

  it("нет провайдера в облаке: совет и кнопка «Добавить в облаке»", async () => {
    const onAdd = vi.fn();
    render(
      <CloudStudiosPanel studios={studios()} now={NOW} onAddProvider={onAdd} />,
    );
    expect(screen.getByTestId("device-ai-advice")).toHaveTextContent(
      "добавьте в облаке провайдера «через мой раннер»",
    );
    await userEvent.click(screen.getByTestId("device-add-provider"));
    expect(onAdd).toHaveBeenCalledWith(
      "e1123c9cadb64dafd48432897072a826",
      expect.objectContaining({ name: "ollama" }),
    );
  });

  it("модель готова: кнопки добавления нет", () => {
    const ready = makeDevice({
      ai: {
        state: "ready",
        endpoints: [makeEndpoint({ state: "ready", provider_name: "Моя" })],
      },
    });
    render(
      <CloudStudiosPanel
        studios={studios({ mine: [ready] })}
        now={NOW}
        onAddProvider={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("device-add-provider")).toBeNull();
    expect(screen.queryByTestId("device-ai-advice")).toBeNull();
  });
});

describe("панель локальной Студии", () => {
  it("сервер, вход, что облако видит, последний сигнал, кто ещё в проекте", () => {
    render(<LocalLinkPanel link={makeLink()} now={NOW} />);
    expect(screen.getByTestId("link-server")).toHaveTextContent(
      "Сервер studio.example.org",
    );
    expect(screen.getByTestId("link-server")).toHaveTextContent(
      "Вы вошли как Анна Петрова",
    );
    expect(screen.getByTestId("link-cloud-sees")).toHaveTextContent("в сети");
    expect(screen.getByTestId("link-last-sent")).toHaveTextContent(
      "последний сигнал отправлен 1 минуту назад",
    );
    expect(screen.getByTestId("link-others")).toHaveTextContent(
      "Борис Смирнов работает локально",
    );
    expect(screen.getByTestId("link-endpoint-ollama")).toHaveTextContent(
      "в облаке не подключён провайдер",
    );
  });

  it("вход истёк: просит войти заново, не показывает сигналов", () => {
    render(
      <LocalLinkPanel
        link={makeLink({
          servers: [makeServer({ state: "expired", cloud: null })],
        })}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("link-relogin")).toBeInTheDocument();
    expect(screen.queryByTestId("link-cloud-sees")).toBeNull();
  });

  it("сигнал не дошёл: виден код ошибки", () => {
    render(
      <LocalLinkPanel
        link={makeLink({
          servers: [
            makeServer({
              last: {
                at: minutesBefore(1),
                ok: false,
                code: "git_server_unreachable",
                interval_s: 60,
                online_window_s: 180,
              },
            }),
          ],
        })}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("link-last-sent")).toHaveTextContent(
      "git_server_unreachable",
    );
  });
});

describe("плашка в заголовке", () => {
  it("облако: плашка открывает панель с подробностями", async () => {
    api.project.mockResolvedValue(studios());
    wrap(<StudioPresence projectId="p1" />);
    const badge = await screen.findByTestId("studio-presence");
    expect(badge).toHaveTextContent("Студия в сети: MacBook Анны");
    await userEvent.click(within(badge).getByRole("button"));
    expect(
      await screen.findByTestId("cloud-studios-panel"),
    ).toBeInTheDocument();
  });

  it("облако: нечего показать, плашки нет", async () => {
    api.project.mockResolvedValue(studios({ mine: [], others: [] }));
    wrap(<StudioPresence projectId="p1" />);
    await waitFor(() => {
      expect(api.project).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("studio-presence")).toBeNull();
  });

  it("локальная Студия: плашка «Облако в сети»", async () => {
    api.mode.value = "local";
    api.link.mockResolvedValue(makeLink());
    wrap(<StudioPresence projectId="p1" />);
    expect(await screen.findByTestId("studio-presence")).toHaveTextContent(
      "Облако в сети",
    );
    expect(api.project).not.toHaveBeenCalled();
  });
});

describe("баннер «Добавить провайдера»", () => {
  it("своя Студия открыла модель без провайдера: кнопка создаёт провайдера через раннер и грузит модели", async () => {
    api.account.mockResolvedValue({
      online_window_s: 180,
      items: [makeDevice()],
    });
    api.create.mockResolvedValue({ id: "prov1", name: "MacBook Анны: ollama" });
    api.fetchModels.mockResolvedValue({ models: ["qwen3:4b-instruct"] });
    api.update.mockResolvedValue({});
    wrap(<StudioProviderBanner />);
    await userEvent.click(
      await screen.findByTestId("studio-provider-banner-add"),
    );
    await waitFor(() => {
      expect(api.update).toHaveBeenCalledWith("prov1", {
        models: ["qwen3:4b-instruct"],
      });
    });
    expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "runner",
        api_key: "",
        runner_id: "5f9f8fde104348e29d9b17298d93152c",
        runner_endpoint: "ollama",
      }),
    );
  });

  it("провайдер уже есть: баннера нет", async () => {
    api.account.mockResolvedValue({
      online_window_s: 180,
      items: [
        makeDevice({
          ai: {
            state: "ready",
            endpoints: [makeEndpoint({ state: "ready", provider_name: "Моя" })],
          },
        }),
      ],
    });
    wrap(<StudioProviderBanner />);
    await waitFor(() => {
      expect(api.account).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("studio-provider-banner")).toBeNull();
  });

  it("Студия не в сети: баннера нет", async () => {
    api.account.mockResolvedValue({
      online_window_s: 180,
      items: [makeDevice({ presence: "offline" })],
    });
    wrap(<StudioProviderBanner />);
    await waitFor(() => {
      expect(api.account).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("studio-provider-banner")).toBeNull();
  });
});
