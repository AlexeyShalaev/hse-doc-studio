import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as sharedLib from "@shared/lib";
import {
  gitSyncApi,
  useSyncUiStore,
  type SyncResult,
} from "@entities/git-sync";
import {
  CONTENTS,
  MERGED,
  PROJECT_ID,
  operation,
  renderExchange,
  resetExchangeEnvironment,
} from "../testing/renderExchange";
import { BundleExchangeDialog } from "./BundleExchangeDialog";

// Окно живёт в заголовке проекта, а закрывает его общее состояние, как в
// виджете SyncCluster.
const Host = () => {
  const isOpen = useSyncUiStore((state) => state.bundleDialogOpen);
  const close = useSyncUiStore((state) => state.closeBundleDialog);
  return (
    <BundleExchangeDialog
      isOpen={isOpen}
      projectId={PROJECT_ID}
      onClose={close}
    />
  );
};

const importFile = async (result: SyncResult) => {
  vi.spyOn(gitSyncApi, "importBundle").mockResolvedValue({
    operation_id: "op-1",
  });
  vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
    operation({
      status: "succeeded",
      phase: "merge",
      finished_at: "2026-10-26T10:01:00Z",
      result,
    }),
  );
  const user = userEvent.setup({ applyAccept: false });
  await user.click(screen.getByRole("button", { name: "Выбрать файл…" }));
  await user.upload(
    await screen.findByTestId("import-input"),
    new File(["bundle"], "coursework.bundle"),
  );
  await user.click(screen.getByRole("button", { name: "Загрузить" }));
  return user;
};

describe("окно «Обмен файлом» в заголовке проекта", () => {
  beforeEach(async () => {
    await resetExchangeEnvironment();
    vi.spyOn(gitSyncApi, "getContents").mockResolvedValue(CONTENTS);
    vi.spyOn(sharedLib, "flushPendingSaves").mockResolvedValue({
      total: 0,
      failed: 0,
    });
    useSyncUiStore.setState({ bundleDialogOpen: true });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useSyncUiStore.setState({
      bundleDialogOpen: false,
      profileDialogOpen: false,
    });
  });

  it("закрывается целиком, когда импорт с конфликтами ведёт на их экран", async () => {
    renderExchange(<Host />);
    const user = await importFile({
      ...MERGED,
      outcome: "conflicts",
      conflicts: { files_total: 2, files_open: 2 },
    });
    await screen.findByTestId("import-result-conflicts");
    await user.click(screen.getByRole("button", { name: "Открыть конфликты" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(useSyncUiStore.getState().bundleDialogOpen).toBe(false);
    expect(screen.getByTestId("location")).toHaveTextContent(
      `/projects/${PROJECT_ID}/sync/conflicts`,
    );
  });

  it("остаётся открытым после обычного слияния, пока человек не закроет его сам", async () => {
    renderExchange(<Host />);
    const user = await importFile(MERGED);
    await screen.findByTestId("import-result-merged");
    await user.click(screen.getByRole("button", { name: "Готово" }));
    expect(
      await screen.findByRole("dialog", { name: "Обмен файлом" }),
    ).toBeInTheDocument();
    expect(useSyncUiStore.getState().bundleDialogOpen).toBe(true);
  });
});
