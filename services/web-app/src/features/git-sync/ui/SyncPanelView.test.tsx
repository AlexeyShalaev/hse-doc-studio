import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SyncStatusView } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import {
  commit,
  connected,
  noRemote,
  runningOperation,
} from "../testing/statusFactory";
import { deriveSyncUi } from "../model/syncUi.model";
import { useSyncText } from "../model/useSyncText";
import { SyncPanelView, type SyncPanelViewProps } from "./SyncPanelView";

const NOW = Date.parse("2026-10-26T10:30:00Z");

const handlers = () => ({
  onSync: vi.fn(),
  onCheck: vi.fn(),
  onCancel: vi.fn(),
  onConnect: vi.fn(),
  onFixAccess: vi.fn(),
  onResolve: vi.fn(),
  onOpenSettings: vi.fn(),
  onOpenProfile: vi.fn(),
  onAcknowledgeSharedFolder: vi.fn(),
  onShowInHistory: vi.fn(),
  onSelectIncoming: vi.fn(),
});

const Harness = ({
  status,
  context = { online: true, readOnly: false },
  ...rest
}: {
  status: SyncStatusView;
  context?: { online: boolean; readOnly: boolean };
} & Partial<SyncPanelViewProps>) => {
  const ui = deriveSyncUi(status, context);
  const text = useSyncText(ui, NOW);
  return (
    <SyncPanelView
      ui={ui}
      status={status}
      text={text}
      now={NOW}
      isStarting={false}
      isChecking={false}
      isCancelling={false}
      selectedIncomingId={null}
      {...handlers()}
      {...rest}
    />
  );
};

describe("SyncPanelView", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  describe("without a repository", () => {
    it("shows the empty state with the connect and bundle buttons", async () => {
      const user = userEvent.setup();
      const onConnect = vi.fn();
      const onBundle = vi.fn();
      render(
        <Harness
          status={noRemote()}
          onConnect={onConnect}
          onBundle={onBundle}
        />,
      );
      expect(screen.getByTestId("sync-panel-empty")).toBeInTheDocument();
      expect(
        screen.getByText("Проект хранится только на этом компьютере"),
      ).toBeInTheDocument();
      await user.click(
        screen.getByRole("button", { name: "Подключить репозиторий" }),
      );
      await user.click(screen.getByRole("button", { name: "Обмен файлом" }));
      expect(onConnect).toHaveBeenCalledTimes(1);
      expect(onBundle).toHaveBeenCalledTimes(1);
    });

    it("hides the bundle button when nobody handles it", () => {
      render(<Harness status={noRemote()} />);
      expect(screen.queryByRole("button", { name: "Обмен файлом" })).toBeNull();
    });

    it("disables connecting in a read-only project and says why", () => {
      render(
        <Harness
          status={noRemote()}
          context={{ online: true, readOnly: true }}
        />,
      );
      expect(
        screen.getByRole("button", { name: "Подключить репозиторий" }),
      ).toBeDisabled();
      expect(screen.getByText("Проект открыт только для чтения.")).toBeTruthy();
    });

    it("asks for the author profile first when it is missing", async () => {
      const user = userEvent.setup();
      const onOpenProfile = vi.fn();
      render(
        <Harness
          status={{ ...noRemote(), profile_ok: false }}
          onOpenProfile={onOpenProfile}
        />,
      );
      expect(screen.getByText(/сначала укажи имя и e-mail/)).toBeTruthy();
      await user.click(screen.getByRole("button", { name: "Указать автора" }));
      expect(onOpenProfile).toHaveBeenCalledTimes(1);
    });
  });

  describe("with a repository", () => {
    it("shows the repository, the counters and the healthy actions", async () => {
      const user = userEvent.setup();
      const onSync = vi.fn();
      const onCheck = vi.fn();
      const onOpenSettings = vi.fn();
      render(
        <Harness
          status={connected()}
          onSync={onSync}
          onCheck={onCheck}
          onOpenSettings={onOpenSettings}
        />,
      );
      expect(screen.getByTestId("sync-panel")).toBeInTheDocument();
      expect(screen.getByText("ivan/coursework")).toBeInTheDocument();
      expect(screen.getByText("main")).toBeInTheDocument();
      expect(screen.getByText("Синхронизировано, 1 час назад")).toBeTruthy();
      await user.click(
        screen.getByRole("button", { name: /Синхронизировать/ }),
      );
      await user.click(
        screen.getByRole("button", { name: "Проверить обновления" }),
      );
      await user.click(
        screen.getByRole("button", { name: "Настройки синхронизации" }),
      );
      expect(onSync).toHaveBeenCalledTimes(1);
      expect(onCheck).toHaveBeenCalledTimes(1);
      expect(onOpenSettings).toHaveBeenCalledTimes(1);
    });

    it("counts incoming and outgoing versions and the files that changed", () => {
      render(
        <Harness
          status={connected({
            ui_state: "diverged",
            relation: "diverged",
            behind: 8,
            behind_files: 5,
            ahead: 2,
            incoming: [commit("a1"), commit("a2")],
            outgoing: [commit("z1", { author: "Иван Смирнов" })],
          })}
        />,
      );
      const stats = document.querySelectorAll(".sync-stat");
      expect(stats).toHaveLength(4);
      expect(within(stats[0] as HTMLElement).getByText("8")).toBeTruthy();
      expect(
        within(stats[0] as HTMLElement).getByText("изменено 5 файлов"),
      ).toBeTruthy();
      expect(within(stats[1] as HTMLElement).getByText("2")).toBeTruthy();
    });

    it("lists the commits, selects an incoming one and shows its details", async () => {
      const user = userEvent.setup();
      const onSelectIncoming = vi.fn();
      const status = connected({
        ui_state: "behind",
        relation: "behind",
        behind: 7,
        incoming: ["a", "b"].map((id) =>
          commit(id, { message: `Входящая ${id}` }),
        ),
      });
      const { rerender } = render(
        <Harness status={status} onSelectIncoming={onSelectIncoming} />,
      );
      const list = screen.getByRole("region", {
        name: "Пришло из репозитория",
      });
      expect(within(list).getByText("и ещё 5")).toBeTruthy();
      await user.click(
        within(list).getByRole("button", { name: /Входящая a/ }),
      );
      expect(onSelectIncoming).toHaveBeenCalledWith("a");
      rerender(
        <Harness
          status={status}
          selectedIncomingId="a"
          incomingDetails={<div>Подробности версии</div>}
        />,
      );
      expect(
        within(list).getByRole("button", { name: /Входящая a/ }),
      ).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByText("Подробности версии")).toBeInTheDocument();
    });

    it("deselects the incoming commit by a second click", async () => {
      const user = userEvent.setup();
      const onSelectIncoming = vi.fn();
      render(
        <Harness
          status={connected({
            ui_state: "behind",
            relation: "behind",
            behind: 1,
            incoming: [commit("a")],
          })}
          selectedIncomingId="a"
          onSelectIncoming={onSelectIncoming}
        />,
      );
      await user.click(screen.getByRole("button", { name: /Версия a/ }));
      expect(onSelectIncoming).toHaveBeenCalledWith(null);
    });

    it("offers to show incoming and unpushed versions in the feed below", async () => {
      const user = userEvent.setup();
      const onShowInHistory = vi.fn();
      render(
        <Harness
          status={connected({
            ui_state: "diverged",
            relation: "diverged",
            behind: 1,
            ahead: 1,
            incoming: [commit("a")],
            outgoing: [commit("z")],
          })}
          onShowInHistory={onShowInHistory}
        />,
      );
      const links = screen.getAllByRole("button", {
        name: "Показать в ленте ниже",
      });
      const [incomingLink, outgoingLink] = links;
      if (!incomingLink || !outgoingLink) throw new Error("links missing");
      await user.click(incomingLink);
      await user.click(outgoingLink);
      expect(onShowInHistory).toHaveBeenNthCalledWith(1, "incoming");
      expect(onShowInHistory).toHaveBeenNthCalledWith(2, "unpushed");
    });

    it("shows the phases while syncing and lets the user cancel", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(
        <Harness
          status={connected({
            ui_state: "syncing",
            operation: runningOperation({ phase: "fetch", percent: 40 }),
          })}
          onCancel={onCancel}
        />,
      );
      expect(screen.getByText(/Получаем изменения 40%/)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Проверить обновления" }),
      ).toBeNull();
      await user.click(screen.getByRole("button", { name: "Отменить" }));
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it("explains the wait for a running build while the sync is queued", () => {
      render(
        <Harness
          status={connected({
            ui_state: "syncing",
            operation: runningOperation({ phase: "queued", percent: null }),
          })}
        />,
      );
      expect(screen.getByText("Ждём окончания сборки")).toBeInTheDocument();
    });

    it("says an operation cannot be cancelled any more", () => {
      render(
        <Harness
          status={connected({
            ui_state: "syncing",
            operation: runningOperation({ cancellable: false, phase: "push" }),
          })}
        />,
      );
      expect(
        screen.getByText("Завершается, отменить уже нельзя"),
      ).toBeInTheDocument();
    });

    it("sends the user to the conflicts and hides the check button", async () => {
      const user = userEvent.setup();
      const onResolve = vi.fn();
      render(
        <Harness
          status={connected({
            ui_state: "conflicts",
            pending: { session_id: "s1", files_total: 4, files_open: 3 },
          })}
          onResolve={onResolve}
        />,
      );
      expect(
        screen.getByText(/Осталось решить файлов: 3 из 4/),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Проверить обновления" }),
      ).toBeNull();
      await user.click(
        screen.getByRole("button", { name: "Разобрать конфликты" }),
      );
      expect(onResolve).toHaveBeenCalledTimes(1);
    });

    it("offers to renew access when the repository rejected it", async () => {
      const user = userEvent.setup();
      const onFixAccess = vi.fn();
      render(
        <Harness
          status={connected({
            ui_state: "auth_failed",
            health: "unauthenticated",
            last_error: {
              code: "auth_failed",
              detail: "Bad credentials",
              at: "2026-10-26T10:00:00Z",
            },
          })}
          onFixAccess={onFixAccess}
        />,
      );
      expect(screen.getByRole("alert")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Обновить доступ" }));
      expect(onFixAccess).toHaveBeenCalledTimes(1);
    });

    it("explains a newer schema and a blocked project without actions to sync", () => {
      render(
        <Harness
          status={connected({
            ui_state: "blocked",
            blocked: {
              reason: "remote_schema_newer",
              required_studio: "0.9.0",
            },
          })}
        />,
      );
      expect(screen.getByText(/Нужна версия 0\.9\.0/)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Синхронизировать/ }),
      ).toBeNull();
    });

    it("shows retry when the repository is unreachable", () => {
      render(
        <Harness
          status={connected({
            ui_state: "offline",
            health: "offline",
            last_error: {
              code: "offline",
              detail: "network is unreachable",
              at: "2026-10-26T10:00:00Z",
            },
          })}
        />,
      );
      expect(screen.getByRole("button", { name: "Повторить" })).toBeEnabled();
    });

    it("warns about a shared folder until acknowledged", async () => {
      const user = userEvent.setup();
      const onAck = vi.fn();
      const { rerender } = render(
        <Harness
          status={connected({
            shared_folder: {
              provider: "yandex_disk",
              root: "/Users/ivan/Yandex.Disk",
              acknowledged: false,
            },
          })}
          onAcknowledgeSharedFolder={onAck}
        />,
      );
      expect(screen.getByText(/Яндекс\.Диск/)).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Понятно" }));
      expect(onAck).toHaveBeenCalledTimes(1);
      rerender(
        <Harness
          status={connected({
            shared_folder: {
              provider: "yandex_disk",
              root: "/Users/ivan/Yandex.Disk",
              acknowledged: true,
            },
          })}
        />,
      );
      expect(screen.queryByText(/Яндекс\.Диск/)).toBeNull();
    });

    it("renders in English", async () => {
      await i18n.changeLanguage("en");
      render(<Harness status={noRemote()} onBundle={vi.fn()} />);
      expect(
        screen.getByText("This project lives only on this computer"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Exchange a file" }),
      ).toBeInTheDocument();
    });
  });
});

describe("отказ pre-receive сервера Студии", () => {
  afterEach(cleanup);

  it("показывает блок «Сервер отклонил отправку» с нарушениями", async () => {
    await i18n.changeLanguage("ru");
    const { SYNC_STATE_FIXTURES } = await import("../fixtures/syncStates");
    const fixture = SYNC_STATE_FIXTURES.find(
      (f) => f.id === "error_push_rejected",
    );
    render(<Harness status={fixture!.build(NOW)} />);
    const block = screen.getByTestId("sync-push-rejected");
    expect(
      within(block).getByText("Сервер отклонил отправку"),
    ).toBeInTheDocument();
    expect(within(block).getAllByRole("listitem")).toHaveLength(2);
    expect(block).toHaveTextContent("[path_outside_scope]");
  });

  it("строки нарушений берутся после двоеточия", async () => {
    const { pushRejectedLines } = await import("./SyncPanelView");
    expect(
      pushRejectedLines("Сервер отклонил:\n- a.tex: вне папки [x]\n\n- b: y"),
    ).toEqual(["- a.tex: вне папки [x]", "- b: y"]);
    expect(pushRejectedLines("без строк")).toEqual([]);
  });
});
