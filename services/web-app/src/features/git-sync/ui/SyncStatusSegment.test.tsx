import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  gitSyncApi,
  useSyncUiStore,
  type SyncStatusView,
} from "@entities/git-sync";
import {
  commit,
  connected,
  noRemote,
  runningOperation,
} from "../testing/statusFactory";
import {
  PROJECT_ID,
  renderSync,
  resetSyncEnvironment,
} from "../testing/renderSync";

vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: { access: { mode: "full", reasons: [] } } }),
}));

import { SyncStatusSegment } from "./SyncStatusSegment";

const mount = async (status: SyncStatusView) => {
  vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(status);
  renderSync(<SyncStatusSegment projectId={PROJECT_ID} />);
  return screen.findByRole("button");
};

describe("SyncStatusSegment", () => {
  beforeEach(resetSyncEnvironment);
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("opens the details panel with Enter and Space", async () => {
    const user = userEvent.setup();
    const segment = await mount(connected());
    segment.focus();
    await user.keyboard("{Enter}");
    expect(useSyncUiStore.getState().popoverOpen).toBe(true);
    await user.keyboard(" ");
    expect(useSyncUiStore.getState().popoverOpen).toBe(false);
    await user.click(segment);
    expect(useSyncUiStore.getState().popoverOpen).toBe(true);
  });

  it("is reachable by Tab and exposes its state to assistive technology", async () => {
    const user = userEvent.setup();
    const segment = await mount(
      connected({ ui_state: "behind", relation: "behind", behind: 3 }),
    );
    await user.tab();
    expect(document.activeElement).toBe(segment);
    expect(segment.getAttribute("aria-haspopup")).toBe("dialog");
    expect(segment.getAttribute("aria-label")).toBe(
      "Синхронизация. Есть изменения: 3",
    );
  });

  it("says that nothing is connected", async () => {
    const segment = await mount(noRemote());
    expect(segment.textContent).toContain("git");
    expect(segment.textContent).toContain("не подключён");
  });

  it("shows the branch and the counts", async () => {
    const segment = await mount(
      connected({
        ui_state: "diverged",
        relation: "diverged",
        behind: 3,
        ahead: 2,
        incoming: [commit("a")],
      }),
    );
    expect(segment.textContent).toContain("main");
    expect(segment.textContent).toContain("3");
    expect(segment.textContent).toContain("2");
  });

  it("names the problem in words, not only in colour", async () => {
    const segment = await mount(
      connected({ ui_state: "auth_failed", health: "unauthenticated" }),
    );
    expect(segment.textContent).toContain("Нет доступа");
    expect(segment.querySelector(".dot.err")).not.toBeNull();
  });

  it("shows the running phase", async () => {
    const segment = await mount(
      connected({
        ui_state: "syncing",
        operation: runningOperation({ phase: "merge", percent: null }),
      }),
    );
    await waitFor(() => {
      expect(segment.textContent).toContain("Объединяем");
    });
    expect(segment.querySelector(".dot.building")).not.toBeNull();
  });

  it("renders nothing for a backend without sync", async () => {
    vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(noRemote(false));
    const { container } = renderSync(
      <SyncStatusSegment projectId={PROJECT_ID} />,
    );
    await waitFor(() => {
      expect(container.querySelector("[role=button]")).toBeNull();
    });
  });
});
