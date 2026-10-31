import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SyncStatusView } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import {
  REMOTE,
  commit,
  connected,
  noRemote,
  runningOperation,
} from "../testing/statusFactory";
import { deriveSyncUi } from "../model/syncUi.model";
import { useSyncText } from "../model/useSyncText";
import { SyncPopover, type SyncPopoverProps } from "./SyncPopover";

const NOW = Date.parse("2026-10-26T10:30:00Z");

const handlers = () => ({
  onSync: vi.fn(),
  onCheck: vi.fn(),
  onCancel: vi.fn(),
  onConnect: vi.fn(),
  onFixAccess: vi.fn(),
  onResolve: vi.fn(),
  onOpenSettings: vi.fn(),
  onOpenHistory: vi.fn(),
  onOpenProfile: vi.fn(),
});

const Harness = ({
  status,
  context = { online: true, readOnly: false },
  ...rest
}: {
  status: SyncStatusView;
  context?: { online: boolean; readOnly: boolean };
} & Partial<SyncPopoverProps>) => {
  const ui = deriveSyncUi(status, context);
  const text = useSyncText(ui, NOW);
  return (
    <SyncPopover
      ui={ui}
      status={status}
      text={text}
      now={NOW}
      isStarting={false}
      isChecking={false}
      isCancelling={false}
      {...handlers()}
      {...rest}
    />
  );
};

describe("SyncPopover", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("invites to connect a repository when there is none", async () => {
    const onConnect = vi.fn();
    render(<Harness status={noRemote()} onConnect={onConnect} />);
    expect(screen.getByText("Репозиторий не подключён")).toBeTruthy();
    await userEvent.click(
      screen.getByRole("button", { name: "Подключить репозиторий" }),
    );
    expect(onConnect).toHaveBeenCalledTimes(1);
  });

  it("explains that a read-only project cannot get a repository", () => {
    render(
      <Harness
        status={noRemote()}
        context={{ online: true, readOnly: true }}
      />,
    );
    expect(screen.getByText("Проект открыт только для чтения.")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Подключить репозиторий" }),
    ).toBeDisabled();
  });

  it("lists up to five commits per side and counts the rest", () => {
    const incoming = ["a", "b", "c", "d", "e"].map((id) =>
      commit(id, { message: `Входящая ${id}` }),
    );
    render(
      <Harness
        status={connected({
          ui_state: "diverged",
          relation: "diverged",
          behind: 8,
          ahead: 1,
          incoming,
          outgoing: [
            commit("z", { message: "Моя правка", author: "Иван Смирнов" }),
          ],
        })}
      />,
    );
    const incomingList = screen.getByRole("region", {
      name: "Пришло из репозитория",
    });
    expect(within(incomingList).getAllByRole("listitem")).toHaveLength(5);
    expect(within(incomingList).getByText("и ещё 3")).toBeTruthy();
    const outgoingList = screen.getByRole("region", { name: "Не отправлено" });
    expect(within(outgoingList).getByText("Моя правка")).toBeTruthy();
    expect(within(outgoingList).queryByText(/и ещё/)).toBeNull();
  });

  it("runs the actions of a healthy state", async () => {
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
    await user.click(screen.getByRole("button", { name: /Синхронизировать/ }));
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

  it("shows the sync phases with a percent, and cancels", async () => {
    const onCancel = vi.fn();
    render(
      <Harness
        status={connected({
          ui_state: "syncing",
          operation: runningOperation({ phase: "push", percent: 72 }),
        })}
        onCancel={onCancel}
      />,
    );
    const steps = screen.getByRole("list", { name: "Этапы синхронизации" });
    const items = within(steps).getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("data-state"))).toEqual([
      "done",
      "done",
      "done",
      "current",
    ]);
    expect(within(items[3] ?? document.body).getByText("72%")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Отменить" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("says when the sync waits for a build and when it cannot be cancelled", () => {
    const { rerender } = render(
      <Harness
        status={connected({
          ui_state: "syncing",
          operation: runningOperation({ phase: "queued", percent: null }),
        })}
      />,
    );
    expect(screen.getByText("Ждём окончания сборки")).toBeTruthy();
    rerender(
      <Harness
        status={connected({
          ui_state: "syncing",
          operation: runningOperation({ cancellable: false }),
        })}
      />,
    );
    expect(screen.queryByRole("button", { name: "Отменить" })).toBeNull();
    expect(screen.getByText("Завершается, отменить уже нельзя")).toBeTruthy();
  });

  it("shows the translated error, a retry, and the technical detail on demand", async () => {
    const user = userEvent.setup();
    const onSync = vi.fn();
    render(
      <Harness
        status={connected({
          ui_state: "error",
          health: "error",
          last_error: {
            code: "remote_moved",
            detail: "non-fast-forward after 3 tries",
            at: "2026-10-26T10:20:00Z",
          },
        })}
        onSync={onSync}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).not.toContain("non-fast-forward");
    await user.click(screen.getByText("Технические подробности"));
    expect(screen.getByLabelText("Технические подробности")).toHaveValue(
      "remote_moved: non-fast-forward after 3 tries",
    );
    await user.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(onSync).toHaveBeenCalledTimes(1);
  });

  it("falls back to the server text for an error code it does not know", () => {
    render(
      <Harness
        status={connected({
          ui_state: "error",
          health: "error",
          last_error: {
            code: "brand_new",
            detail: "Только сервер знает это",
            at: "2026-10-26T10:20:00Z",
          },
        })}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "Только сервер знает это",
    );
  });

  it("offers to update the access when it was refused", async () => {
    const onFixAccess = vi.fn();
    render(
      <Harness
        status={connected({
          ui_state: "auth_failed",
          health: "unauthenticated",
          last_error: {
            code: "auth_failed",
            detail: "denied",
            at: "2026-10-26T10:20:00Z",
          },
        })}
        onFixAccess={onFixAccess}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Обновить доступ" }),
    );
    expect(onFixAccess).toHaveBeenCalledTimes(1);
  });

  it("points to the conflict screen with the number of open files", async () => {
    const onResolve = vi.fn();
    render(
      <Harness
        status={connected({
          ui_state: "conflicts",
          pending: { session_id: "s", files_total: 5, files_open: 3 },
        })}
        onResolve={onResolve}
      />,
    );
    expect(screen.getByText("Осталось решить файлов: 3 из 5")).toBeTruthy();
    await userEvent.click(
      screen.getByRole("button", { name: "Разобрать конфликты" }),
    );
    expect(onResolve).toHaveBeenCalledTimes(1);
  });

  it("asks for the author when the profile is missing", async () => {
    const onOpenProfile = vi.fn();
    render(
      <Harness
        status={connected({
          ui_state: "blocked",
          blocked: { reason: "profile_required" },
          profile_ok: false,
        })}
        onOpenProfile={onOpenProfile}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Указать автора" }),
    );
    expect(onOpenProfile).toHaveBeenCalledTimes(1);
  });

  it("names the Studio version a newer project needs", () => {
    render(
      <Harness
        status={connected({
          ui_state: "blocked",
          blocked: { reason: "remote_schema_newer", required_studio: "0.4.0" },
        })}
      />,
    );
    expect(screen.getByText(/Нужна версия 0\.4\.0 или новее/)).toBeTruthy();
  });

  it("links to the repository page and shows the branch mapping", () => {
    render(
      <Harness
        status={connected({
          remote: {
            ...(connected().remote ?? REMOTE),
            branch: "main",
            local_branch: "master",
          },
        })}
      />,
    );
    const link = screen.getByRole("link", { name: "Открыть в браузере" });
    expect(link.getAttribute("href")).toBe(
      "https://github.com/ivan/coursework",
    );
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(
      screen.getByText("main").closest(".chip")?.getAttribute("title"),
    ).toBe("Локальная ветка master отправляется в main");
  });

  it("says the browser is offline and disables the actions", () => {
    render(
      <Harness
        status={connected({
          ui_state: "behind",
          relation: "behind",
          behind: 1,
        })}
        context={{ online: false, readOnly: false }}
      />,
    );
    expect(screen.getByText(/У браузера нет сети/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Повторить/ })).toBeDisabled();
  });

  it("renders in English", async () => {
    await i18n.changeLanguage("en");
    render(<Harness status={noRemote()} />);
    expect(
      screen.getByRole("button", { name: "Connect a repository" }),
    ).toBeTruthy();
    expect(screen.getByText("No repository connected")).toBeTruthy();
  });
});

describe("SyncPopover auto sync", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  const auto = (
    patch: Partial<NonNullable<SyncPopoverProps["autoSync"]>> = {},
  ): NonNullable<SyncPopoverProps["autoSync"]> => ({
    available: true,
    enabled: true,
    explicit: false,
    phase: "watching",
    stop: null,
    failures: 0,
    isSaving: false,
    setEnabled: vi.fn(),
    ...patch,
  });

  it("offers the auto sync switch for a connected project", async () => {
    const setEnabled = vi.fn();
    render(<Harness status={connected()} autoSync={auto({ setEnabled })} />);

    await userEvent.click(screen.getByRole("switch"));

    expect(setEnabled).toHaveBeenCalledWith(false);
  });

  it("shows the last PDF upload only for a Studio server project", () => {
    const { rerender } = render(
      <Harness status={connected()} autoSync={auto()} />,
    );
    expect(screen.queryByTestId("pdf-upload-line")).toBeNull();

    rerender(
      <Harness
        status={connected({
          pdf_upload: { enabled: true, available: true, last: null },
        })}
        autoSync={auto()}
      />,
    );
    expect(screen.getByTestId("pdf-upload-line")).toBeTruthy();
  });

  it("has no switch without a repository or when the client cannot sync", () => {
    const { rerender } = render(
      <Harness status={noRemote()} autoSync={auto({ available: false })} />,
    );
    expect(screen.queryByRole("switch")).toBeNull();

    rerender(
      <Harness status={connected()} autoSync={auto({ available: false })} />,
    );
    expect(screen.queryByRole("switch")).toBeNull();
  });
});
