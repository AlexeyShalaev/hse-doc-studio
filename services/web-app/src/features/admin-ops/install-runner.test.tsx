import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { InstallJob } from "@entities/session";
import { opsApi } from "./api/opsApi";
import { ensureAdminOpsLocales } from "./lib/locales";
import { InstallRunnerDialog } from "./ui/InstallRunnerDialog";

const failedJob: InstallJob = {
  id: "j1",
  target: "docker",
  name: "hse-runner-a1b2c3",
  state: "failed",
  steps: [
    { key: "token", state: "done", detail: "" },
    { key: "pull", state: "failed", detail: "pull access denied" },
    { key: "start", state: "pending", detail: "" },
    { key: "register", state: "pending", detail: "" },
  ],
  error_code: "image_pull_failed",
  error_detail: "pull access denied",
  created_at: "2026-11-06T12:00:00Z",
};

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>
  </I18nextProvider>
);

describe("установка раннера: отказы и повтор", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
    vi.spyOn(opsApi, "localCapabilities").mockResolvedValue({
      docker: { available: true, reason: null },
      kubernetes: { available: false, reason: "no_permission" },
    });
    vi.spyOn(opsApi, "localInstances").mockResolvedValue([]);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("ошибка шага объяснена по-человечески, повтор запускает установку заново", async () => {
    const start = vi
      .spyOn(opsApi, "startLocalInstall")
      .mockResolvedValue({ ...failedJob, state: "running", error_code: null });
    vi.spyOn(opsApi, "installJob").mockResolvedValue(failedJob);
    const user = userEvent.setup();
    render(
      wrap(
        <InstallRunnerDialog
          isOpen
          onClose={vi.fn()}
          onOpenCommand={vi.fn()}
        />,
      ),
    );

    await user.click(await screen.findByTestId("install-local-docker-start"));
    const failed = await screen.findByTestId("install-failed");
    expect(failed).toHaveTextContent("Не удалось скачать образ раннера");
    expect(failed).toHaveTextContent("pull access denied");
    expect(screen.getByTestId("install-step-pull")).toHaveAttribute(
      "data-state",
      "failed",
    );

    await user.click(screen.getByTestId("install-retry"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledTimes(2);
    });
  });

  it("недоступный способ не показывает кнопку, а объясняет причину", async () => {
    render(
      wrap(
        <InstallRunnerDialog
          isOpen
          onClose={vi.fn()}
          onOpenCommand={vi.fn()}
        />,
      ),
    );

    expect(
      await screen.findByTestId("install-local-kubernetes-unavailable"),
    ).toHaveTextContent("нет прав создавать Deployment");
    expect(screen.queryByTestId("install-local-kubernetes-start")).toBeNull();
  });

  it("занятая установка показывает понятное сообщение", async () => {
    const { ApiError } = await import("@shared/api");
    vi.spyOn(opsApi, "startLocalInstall").mockRejectedValue(
      new ApiError("busy", "install_busy", 409),
    );
    const user = userEvent.setup();
    render(
      wrap(
        <InstallRunnerDialog
          isOpen
          onClose={vi.fn()}
          onOpenCommand={vi.fn()}
        />,
      ),
    );

    await user.click(await screen.findByTestId("install-local-docker-start"));

    expect(
      await screen.findByTestId("install-start-failure"),
    ).toHaveTextContent("уже идёт");
  });

  it("лимиты уходят только для кластера и только заполненные поля", async () => {
    vi.spyOn(opsApi, "localCapabilities").mockResolvedValue({
      docker: { available: true, reason: null },
      kubernetes: { available: true, reason: null },
    });
    const start = vi
      .spyOn(opsApi, "startLocalInstall")
      .mockResolvedValue({ ...failedJob, state: "running", error_code: null });
    vi.spyOn(opsApi, "installJob").mockResolvedValue(failedJob);
    const user = userEvent.setup();
    render(
      wrap(
        <InstallRunnerDialog
          isOpen
          onClose={vi.fn()}
          onOpenCommand={vi.fn()}
        />,
      ),
    );

    await user.click(
      await screen.findByText("Лимиты ресурсов (установка в кластер)"),
    );
    await user.type(screen.getByTestId("install-limit-build_memory"), "6Gi");
    await user.click(screen.getByTestId("install-local-kubernetes-start"));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("kubernetes", {
        name: "",
        concurrency: 1,
        resources: { build_memory: "6Gi" },
      });
    });
  });

  it("границы нарушены: бэкенд отказал, форма объясняет формат и границы", async () => {
    vi.spyOn(opsApi, "localCapabilities").mockResolvedValue({
      docker: { available: false, reason: "disabled" },
      kubernetes: { available: true, reason: null },
    });
    const { ApiError } = await import("@shared/api");
    vi.spyOn(opsApi, "startLocalInstall").mockRejectedValue(
      new ApiError("bad", "invalid_resources", 422),
    );
    const user = userEvent.setup();
    render(
      wrap(
        <InstallRunnerDialog
          isOpen
          onClose={vi.fn()}
          onOpenCommand={vi.fn()}
        />,
      ),
    );

    await user.click(
      await screen.findByTestId("install-local-kubernetes-start"),
    );

    expect(
      await screen.findByTestId("install-start-failure"),
    ).toHaveTextContent("вне допустимых границ");
  });
});
