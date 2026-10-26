import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { gitSyncApi, type SyncStatusView } from "@entities/git-sync";
import { connected } from "../testing/statusFactory";
import {
  PROJECT_ID,
  renderSync,
  resetSyncEnvironment,
} from "../testing/renderSync";

vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: { access: { mode: "full", reasons: [] } } }),
}));

import { ConflictBanner } from "./ConflictBanner";

const CONFLICTS: SyncStatusView = connected({
  ui_state: "conflicts",
  pending: { session_id: "s", files_total: 5, files_open: 3 },
});

describe("ConflictBanner", () => {
  beforeEach(resetSyncEnvironment);
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("tells that sync is not finished, with the numbers, and opens the screen", async () => {
    vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(CONFLICTS);
    renderSync(<ConflictBanner projectId={PROJECT_ID} />);
    const banner = await screen.findByRole("status");
    expect(banner.textContent).toContain("Синхронизация не завершена");
    expect(banner.textContent).toContain("Осталось решить файлов: 3 из 5");
    await userEvent.click(screen.getByRole("button", { name: "Разобрать" }));
    expect(screen.getByTestId("location").textContent).toBe(
      `/projects/${PROJECT_ID}/sync/conflicts`,
    );
  });

  it("is hidden on the conflict screen itself", async () => {
    vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(CONFLICTS);
    renderSync(<ConflictBanner projectId={PROJECT_ID} />, {
      path: `/projects/${PROJECT_ID}/sync/conflicts`,
    });
    await waitFor(() => {
      expect(gitSyncApi.getStatus).toHaveBeenCalled();
    });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("is hidden without conflicts", async () => {
    vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(connected());
    renderSync(<ConflictBanner projectId={PROJECT_ID} />);
    await waitFor(() => {
      expect(gitSyncApi.getStatus).toHaveBeenCalled();
    });
    expect(screen.queryByRole("status")).toBeNull();
  });
});
