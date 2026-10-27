import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import {
  NO_REMOTE_STATUS,
  gitSyncKeys,
  toStatusView,
  type GitContents,
  type GitOperation,
  type SyncResult,
  type SyncStatusView,
} from "@entities/git-sync";
import { useToastStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";

export const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

// Показывает адрес, чтобы тест видел, куда увёл переход.
const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

export const renderExchange = (
  ui: ReactElement,
  options: { status?: SyncStatusView } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  if (options.status) {
    client.setQueryData(gitSyncKeys.status(PROJECT_ID), options.status);
  }
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`/projects/${PROJECT_ID}/project-settings/sync`]}
      >
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, client };
};

export const resetExchangeEnvironment = async (): Promise<void> => {
  await i18n.changeLanguage("ru");
  useToastStore.getState().clear();
};

export const CONTENTS: GitContents = {
  files: 86,
  bytes: 14_800_000,
  commits: 142,
  bot_authored_commits: 0,
  signatures: 2,
  nda_files: 0,
  pdf_tracked: true,
  largest: [],
  over_limit: [],
  lfs_pointers: 0,
};

export const readOnlyStatus = (): SyncStatusView =>
  toStatusView({
    ...NO_REMOTE_STATUS,
    ui_state: "blocked",
    blocked: { reason: "read_only", required_studio: null },
  });

export const MERGED: SyncResult = {
  outcome: "merged",
  pulled_commits: 3,
  pushed_commits: 0,
  merge_commit: "abc1234",
  files_changed: 7,
  auto: [{ path: "chapters/intro.tex", action: "merged", copy_path: null }],
  conflicts: null,
  warnings: [],
};

export const operation = (
  overrides: Partial<GitOperation> = {},
): GitOperation => ({
  id: "op-1",
  kind: "bundle_import",
  project_id: PROJECT_ID,
  status: "running",
  phase: "verify",
  percent: null,
  message: null,
  cancellable: true,
  started_at: "2026-10-26T10:00:00Z",
  finished_at: null,
  result: null,
  error: null,
  ...overrides,
});
