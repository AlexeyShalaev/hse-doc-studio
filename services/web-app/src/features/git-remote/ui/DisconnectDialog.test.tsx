import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { useToastStore } from "@shared/lib";
import { gitSyncApi } from "@entities/git-sync";
import { PAT, PROJECT_ID, REMOTE } from "../testing/connectFixtures";
import {
  renderSettings,
  resetSettingsEnvironment,
} from "../testing/renderSettings";
import { DisconnectDialog } from "./DisconnectDialog";

const mount = (
  props: Partial<React.ComponentProps<typeof DisconnectDialog>> = {},
) => {
  const onClose = vi.fn();
  renderSettings(
    <DisconnectDialog
      isOpen
      projectId={PROJECT_ID}
      remote={REMOTE}
      unsent={0}
      credential={PAT}
      onClose={onClose}
      {...props}
    />,
  );
  return { onClose };
};

describe("окно отключения репозитория", () => {
  beforeEach(async () => {
    await resetSettingsEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("объясняет, что останется, и называет репозиторий", () => {
    mount();
    const dialog = screen.getByRole("dialog", {
      name: "Отключить репозиторий?",
    });
    expect(dialog).toHaveTextContent("github.com/hse-team/paper");
    expect(dialog).toHaveTextContent("Локальная история останется");
    expect(screen.queryByText(/Не отправлен/)).toBeNull();
  });

  it("предупреждает о неотправленных версиях с правильным числом", () => {
    mount({ unsent: 3 });
    expect(
      screen.getByText(/Не отправлено 3 версии\. После отключения/),
    ).toBeInTheDocument();
  });

  it("по умолчанию отключает, не трогая сохранённый доступ", async () => {
    const user = userEvent.setup();
    const disconnect = vi
      .spyOn(gitSyncApi, "disconnectRemote")
      .mockResolvedValue();
    const { onClose } = mount();
    const forget = screen.getByRole("checkbox", {
      name: /Удалить сохранённый доступ «GitHub, рабочий»/,
    });
    expect(forget).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() => {
      expect(disconnect).toHaveBeenCalledWith(PROJECT_ID, false);
    });
    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
    expect(
      useToastStore
        .getState()
        .toasts.some((toast) => toast.message === "Репозиторий отключён"),
    ).toBe(true);
  });

  it("с отметкой просит сервер забыть и доступ", async () => {
    const user = userEvent.setup();
    const disconnect = vi
      .spyOn(gitSyncApi, "disconnectRemote")
      .mockResolvedValue();
    mount();
    await user.click(
      screen.getByRole("checkbox", { name: /Удалить сохранённый доступ/ }),
    );
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() => {
      expect(disconnect).toHaveBeenCalledWith(PROJECT_ID, true);
    });
  });

  it("если доступом пользуются другие проекты, удалить его отсюда нельзя", async () => {
    const user = userEvent.setup();
    const disconnect = vi
      .spyOn(gitSyncApi, "disconnectRemote")
      .mockResolvedValue();
    mount({
      credential: {
        ...PAT,
        used_by: [
          { project_id: PROJECT_ID, name: "Эта работа" },
          { project_id: "p2", name: "Диплом" },
          { project_id: "p3", name: "Курсовая" },
        ],
      },
    });
    const forget = screen.getByRole("checkbox", {
      name: /Удалить сохранённый доступ/,
    });
    expect(forget).toBeDisabled();
    expect(
      screen.getByText(
        /Этим доступом пользуются и другие проекты: Диплом, Курсовая/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Эта работа")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() => {
      expect(disconnect).toHaveBeenCalledWith(PROJECT_ID, false);
    });
  });

  it("у репозитория без доступа отметки об удалении нет", () => {
    mount({ credential: null, remote: { ...REMOTE, credential: null } });
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("при сбое остаётся открытым и показывает причину", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitSyncApi, "disconnectRemote").mockRejectedValue(
      new ApiError("Идёт синхронизация.", "sync_busy", 409),
    );
    const { onClose } = mount();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Отключить" })).toBeEnabled();
  });

  it("«Отмена» закрывает окно и ничего не отправляет", async () => {
    const user = userEvent.setup();
    const disconnect = vi.spyOn(gitSyncApi, "disconnectRemote");
    const { onClose } = mount();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(disconnect).not.toHaveBeenCalled();
  });
});
