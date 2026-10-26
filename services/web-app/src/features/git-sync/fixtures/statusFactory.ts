import {
  NO_REMOTE_STATUS,
  toStatusView,
  type GitCommitBrief,
  type GitRemoteInfo,
  type GitStatus,
  type SyncStatusView,
} from "@entities/git-sync";

// Общие заготовки состояния для тестов синхронизации.

export const REMOTE: GitRemoteInfo = {
  display_url: "https://github.com/ivan/coursework",
  kind: "https",
  host: "github.com",
  provider: "github",
  web_url: "https://github.com/ivan/coursework",
  branch: "main",
  local_branch: "main",
  credential: null,
  insecure_http: false,
};

export const commit = (
  id: string,
  overrides: Partial<GitCommitBrief> = {},
): GitCommitBrief => ({
  id,
  short_id: id.slice(0, 7),
  message: `Версия ${id}`,
  author: "Анна Петрова",
  author_email: "anna@example.com",
  created_at: "2026-10-26T10:00:00Z",
  kind: "edit",
  ...overrides,
});

export const connected = (
  overrides: Partial<GitStatus> = {},
  supported = true,
): SyncStatusView =>
  toStatusView(
    {
      ...NO_REMOTE_STATUS,
      connected: true,
      ui_state: "up_to_date",
      remote: REMOTE,
      relation: "in_sync",
      last_fetch_at: "2026-10-26T10:00:00Z",
      last_fetch_ok_at: "2026-10-26T10:00:00Z",
      last_sync_at: "2026-10-26T09:00:00Z",
      auto_fetch: { enabled: true, interval_s: 300, next_fetch_at: null },
      ...overrides,
    },
    supported,
  );

export const noRemote = (supported = true): SyncStatusView =>
  toStatusView(NO_REMOTE_STATUS, supported);

export const runningOperation = (
  overrides: Partial<NonNullable<GitStatus["operation"]>> = {},
): NonNullable<GitStatus["operation"]> => ({
  id: "op-1",
  kind: "sync",
  phase: "fetch",
  percent: 40,
  cancellable: true,
  started_at: "2026-10-26T10:00:00Z",
  ...overrides,
});
