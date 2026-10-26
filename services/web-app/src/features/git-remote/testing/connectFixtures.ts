import type {
  GitCredential,
  GitCredentialCheck,
  Probe,
} from "@entities/git-remote";
import {
  NO_REMOTE_STATUS,
  toStatusView,
  type GitContents,
  type GitRemoteInfo,
  type GitStatus,
  type SyncStatusView,
} from "@entities/git-sync";
import type { Profile } from "@entities/profile";

// Заготовки для тестов окна подключения.

export const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

export const CUSTOM_PROFILE: Profile = {
  name: "Иван Смирнов",
  email: "ivan@edu.hse.ru",
  effective_name: "Иван Смирнов",
  effective_email: "ivan@edu.hse.ru",
  is_default: false,
  commit_preview: "Иван Смирнов <ivan@edu.hse.ru>",
};

export const DEFAULT_PROFILE: Profile = {
  name: null,
  email: null,
  effective_name: "HSE Doc Studio",
  effective_email: "studio@hse-doc-studio.local",
  is_default: true,
  commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
};

export const CONTENTS: GitContents = {
  files: 86,
  bytes: 14_800_000,
  commits: 142,
  bot_authored_commits: 0,
  signatures: 2,
  nda_files: 0,
  pdf_tracked: true,
  largest: [
    { path: "images/architecture.png", bytes: 3_400_000 },
    { path: "references.bib", bytes: 120_000 },
  ],
  over_limit: [],
  lfs_pointers: 0,
};

export const noRemoteStatus = (
  overrides: Partial<GitStatus> = {},
): SyncStatusView => toStatusView({ ...NO_REMOTE_STATUS, ...overrides });

export const REMOTE: GitRemoteInfo = {
  display_url: "https://github.com/hse-team/paper",
  kind: "https",
  host: "github.com",
  provider: "github",
  web_url: "https://github.com/hse-team/paper",
  branch: "main",
  local_branch: "main",
  credential: { id: "cred-pat", label: "GitHub, рабочий", kind: "pat" },
  insecure_http: false,
};

export const connectedStatus = (
  overrides: Partial<GitStatus> = {},
): SyncStatusView =>
  toStatusView({
    ...NO_REMOTE_STATUS,
    connected: true,
    ui_state: "auth_failed",
    health: "unauthenticated",
    remote: REMOTE,
    ...overrides,
  });

export const PAT: GitCredential = {
  id: "cred-pat",
  kind: "pat",
  label: "GitHub, рабочий",
  host: "github.com",
  username: null,
  status: "auth_failed",
  token_family: "github_pat",
  public_key: null,
  fingerprint_sha256: null,
  created_at: "2026-09-01T10:00:00Z",
  last_used_at: "2026-10-25T10:00:00Z",
  expires_at: null,
  used_by: [],
};

export const SSH_KEY: GitCredential = {
  id: "cred-ssh",
  kind: "ssh_key",
  label: "Ключ: GitHub, github.com",
  host: "github.com",
  username: null,
  status: "unverified",
  token_family: null,
  public_key:
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyOnlyForTests hse-doc-studio",
  fingerprint_sha256: "SHA256:Zk3p0V7m1sJrQxM2n9LdTqEoUy5aBc8HwXf4GiRvN6A",
  created_at: "2026-10-26T10:00:00Z",
  last_used_at: null,
  expires_at: null,
  used_by: [],
};

export const GITHUB_INFO = {
  id: "github",
  detected_by: "host",
  version: null,
} as const;

/** Проверка токена: всё в порядке, права достаточны. */
export const CHECK_OK: GitCredentialCheck = {
  credential: PAT,
  provider_info: GITHUB_INFO,
  token_info: {
    login: "ivan-smirnov",
    scopes: ["repo"],
    expires_at: null,
    sufficiency: "sufficient",
    missing: [],
  },
};

export const PROBE_PROJECT = {
  id: PROJECT_ID,
  name: "Курсовая работа",
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  template_version: "1.2.0",
  kind: "project",
  staffing: "team",
  authors_count: 2,
};

export const makeProbe = (overrides: Partial<Probe> = {}): Probe => ({
  ok: true,
  error: null,
  url: {
    display_url: "https://github.com/hse-team/paper",
    kind: "https",
    host: "github.com",
    provider: "github",
    owner: "hse-team",
    repo: "paper",
    token_stripped: false,
  },
  provider_info: GITHUB_INFO,
  token_info: null,
  reachable: true,
  auth_ok: true,
  empty: false,
  default_branch: "main",
  branches: ["main", "develop"],
  relation: "same_project",
  project: PROBE_PROJECT,
  schema_access: "full",
  required_studio: null,
  template_available: true,
  ...overrides,
});

export const failedProbe = (
  code: string,
  detail = "",
  extra: Partial<Probe> = {},
  hostKeys: { type: string; fingerprint_sha256: string }[] | null = null,
): Probe =>
  makeProbe({
    ok: false,
    error: { code, detail, host_keys: hostKeys },
    auth_ok: false,
    relation: "unknown",
    project: null,
    ...extra,
  });
