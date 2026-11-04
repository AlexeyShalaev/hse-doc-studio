import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NOW, makeDevice, makeLink } from "@entities/connected-device/testing";
import { EndpointCloudState } from "@entities/connected-device";
import { AccountDevicesSection } from "./ui/AccountDevicesSection";
import { LocalLinkSection } from "./ui/LocalLinkSection";

const api = vi.hoisted(() => ({
  account: vi.fn(),
  forget: vi.fn(),
  device: vi.fn(),
  rename: vi.fn(),
  link: vi.fn(),
  mode: { value: "server" },
}));

vi.mock("@entities/connected-device/api/deviceApi", () => ({
  deviceApi: { account: api.account, forget: api.forget, project: vi.fn() },
  studioLinkApi: {
    device: api.device,
    rename: api.rename,
    link: api.link,
  },
}));

vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useBootstrap: () => ({ data: { mode: api.mode.value } }),
}));

const wrap = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>,
  );

beforeEach(() => {
  vi.setSystemTime(NOW);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("«Мои Студии» в облаке", () => {
  it("список своих устройств; «Забыть устройство» с подтверждением", async () => {
    api.mode.value = "server";
    api.account.mockResolvedValue({
      online_window_s: 180,
      items: [
        makeDevice(),
        makeDevice({
          id: "c".repeat(32),
          name: "Рабочий ПК",
          presence: "offline",
        }),
      ],
    });
    api.forget.mockResolvedValue({});
    wrap(<AccountDevicesSection />);
    expect(await screen.findAllByTestId("device-card")).toHaveLength(2);
    await userEvent.click(screen.getAllByTestId("device-forget")[1]!);
    await userEvent.click(await screen.findByTestId("device-forget-confirm"));
    await waitFor(() => {
      expect(api.forget).toHaveBeenCalledWith("c".repeat(32));
    });
  });

  it("в локальной Студии раздела нет", () => {
    api.mode.value = "local";
    wrap(<AccountDevicesSection />);
    expect(screen.queryByTestId("account-devices")).toBeNull();
    expect(api.account).not.toHaveBeenCalled();
  });
});

describe("«Связь с облаком» в настройках локальной Студии", () => {
  it("имя устройства сохраняется и сбрасывается к имени машины", async () => {
    api.mode.value = "local";
    api.device.mockResolvedValue({
      device_id: "a".repeat(32),
      name: "MacBook Анны",
      default_name: "MacBook-Air-Anna",
      custom: true,
    });
    api.link.mockResolvedValue(makeLink());
    api.rename.mockResolvedValue({});
    wrap(<LocalLinkSection />);
    const input = await screen.findByTestId("device-name-input");
    await userEvent.clear(input);
    await userEvent.type(input, "Офисный Mac");
    await userEvent.click(screen.getByTestId("device-name-save"));
    await waitFor(() => {
      expect(api.rename).toHaveBeenCalledWith("Офисный Mac");
    });
    await userEvent.click(screen.getByTestId("device-name-reset"));
    await waitFor(() => {
      expect(api.rename).toHaveBeenLastCalledWith(null);
    });
    expect(await screen.findByTestId("link-server")).toBeInTheDocument();
  });

  it("слишком длинное имя не сохраняется", async () => {
    api.mode.value = "local";
    api.device.mockResolvedValue({
      device_id: "a".repeat(32),
      name: "Mac",
      default_name: "Mac",
      custom: false,
    });
    api.link.mockResolvedValue(makeLink({ servers: [] }));
    wrap(<LocalLinkSection />);
    const input = await screen.findByTestId("device-name-input");
    await userEvent.clear(input);
    await userEvent.type(input, "x".repeat(65));
    expect(screen.getByTestId("device-name-save")).toBeDisabled();
  });
});

describe("состояние открытой модели в облаке", () => {
  it("видно причину и совет: провайдера в облаке нет", () => {
    render(<EndpointCloudState name="ollama" announced link={makeLink()} />);
    const state = screen.getByTestId("endpoint-cloud-state-ollama");
    expect(state).toHaveAttribute("data-state", "no_provider");
    expect(state).toHaveTextContent("в облаке не подключён провайдер");
    expect(state).toHaveTextContent("«через мой раннер»");
  });

  it("адрес ещё не дошёл до сервера", () => {
    render(
      <EndpointCloudState name="ollama" announced={false} link={makeLink()} />,
    );
    expect(screen.getByTestId("endpoint-cloud-state-ollama")).toHaveAttribute(
      "data-state",
      "not_opened",
    );
  });

  it("связи с облаком нет: состояние неизвестно", () => {
    render(<EndpointCloudState name="ollama" announced link={undefined} />);
    expect(screen.getByTestId("endpoint-cloud-state-ollama")).toHaveAttribute(
      "data-state",
      "unknown",
    );
  });
});
