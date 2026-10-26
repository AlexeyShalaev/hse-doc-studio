import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  NO_REMOTE_STATUS,
  gitSyncKeys,
  toStatusView,
  type GitStatus,
  type SyncStatusView,
} from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";

vi.mock("@entities/project", () => ({
  useProject: () => ({
    data: {
      id: "p1",
      staffing: "solo",
      kind: "coursework",
      lang: "ru",
      lock: { pack_id: "a", template_id: "b", version: "1" },
    },
  }),
}));
vi.mock("@entities/document", () => ({
  useDocuments: () => ({ data: [] }),
}));
vi.mock("@entities/template-catalog", () => ({
  useVersionDetail: () => ({ data: undefined }),
}));
vi.mock("@features/template-update", () => ({
  useTemplateUpdateSignal: () => ({ hasSignal: false, markers: [] }),
}));

import { ProjectSettingsPanel } from "./ProjectSettingsPanel";

const PROJECT_ID = "p1";

const status = (overrides: Partial<GitStatus> = {}): SyncStatusView =>
  toStatusView({
    ...NO_REMOTE_STATUS,
    connected: true,
    ui_state: "up_to_date",
    relation: "in_sync",
    ...overrides,
  });

const mount = (value: SyncStatusView, onSelect = vi.fn()) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(gitSyncKeys.status(PROJECT_ID), value);
  render(
    <QueryClientProvider client={client}>
      <ProjectSettingsPanel
        projectId={PROJECT_ID}
        activeSection="general"
        onSelectSection={onSelect}
      />
    </QueryClientProvider>,
  );
  return onSelect;
};

describe("оглавление настроек проекта: группа «Синхронизация»", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("есть в оглавлении и ведёт на свою страницу", async () => {
    const user = userEvent.setup();
    const onSelect = mount(toStatusView(NO_REMOTE_STATUS));
    await user.click(screen.getByRole("button", { name: /Синхронизация/ }));
    expect(onSelect).toHaveBeenCalledWith("sync");
  });

  it("на старом бэкенде группы нет", () => {
    mount(toStatusView(NO_REMOTE_STATUS, false));
    expect(screen.queryByRole("button", { name: /Синхронизация/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Проект/ })).toBeInTheDocument();
  });

  it("когда сказать нечего, точки нет", () => {
    mount(status());
    expect(screen.queryByTestId("sync-group-dot")).toBeNull();
  });

  it("при конфликтах рядом с группой красная точка с понятной подписью", () => {
    mount(
      status({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 3, files_open: 2 },
      }),
    );
    const group = screen.getByRole("button", { name: /Синхронизация/ });
    const dot = within(group).getByTestId("sync-group-dot");
    expect(dot).toHaveClass("dot", "err");
    expect(dot).toHaveAccessibleName("Есть конфликты");
  });

  it("при отказе входа точка жёлтая", () => {
    mount(status({ ui_state: "auth_failed", health: "unauthenticated" }));
    const dot = screen.getByTestId("sync-group-dot");
    expect(dot).toHaveClass("warn");
    expect(dot).toHaveAccessibleName("Нет доступа");
  });

  it("новое от коллег отмечено спокойной синей точкой", () => {
    mount(
      status({
        ui_state: "behind",
        relation: "behind",
        behind: 2,
      }),
    );
    expect(screen.getByTestId("sync-group-dot")).toHaveClass("info");
  });
});
