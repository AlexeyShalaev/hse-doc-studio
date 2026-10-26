import type {
  CloneResult,
  GitCommitBrief,
  GitOperation,
  GitRemoteInfo,
  GitStatus,
  SyncResult,
} from "@entities/git-sync";
import type { GitCredential, GitHost } from "@entities/git-remote";
import type { Profile } from "@entities/profile";
import {
  MINUTE,
  fakeSha,
  fakeUuid,
  isoAgo,
  isoAt,
  nextId,
  nowMs,
} from "./clock";
import {
  applyDrafts,
  buildConflictSession,
  type DemoConflictSession,
} from "./conflictData";
import { incomingCommits, outgoingCommits } from "./people";

// --- мир демо ---------------------------------------------------------------------
// Всё состояние живёт в памяти вкладки и сбрасывается при смене сценария.

export type DemoProjectGit = {
  remote: GitRemoteInfo | null;
  relation: string;
  ahead: number;
  behind: number;
  behindFiles: number;
  health: string;
  lastError: { code: string; detail: string; at: string } | null;
  blocked: { reason: string; required_studio?: string | null } | null;
  incoming: GitCommitBrief[];
  outgoing: GitCommitBrief[];
  operationId: string | null;
  lastFetchAt: string | null;
  lastFetchOkAt: string | null;
  lastSyncAt: string | null;
  lastSync: GitStatus["last_sync"];
  autoFetch: { enabled: boolean; interval_s: number };
  sharedFolder: { provider: string; root: string } | null;
  sharedAck: boolean;
  botAuthored: number;
  // Что покажет состав проекта перед подключением (GET /git/contents).
  ndaFiles: number;
  lfsPointers: number;
  overLimit: { path: string; bytes: number; limit: number }[];
  conflict: DemoConflictSession | null;
  // Слияние при следующей синхронизации закончится конфликтом.
  willConflict: boolean;
  // Слияние при следующей синхронизации сломается этой ошибкой (код и текст).
  failWith: { code: string; detail: string } | null;
};

export type OperationStep = { phase: string; ms: number };

export type DemoOperation = {
  id: string;
  kind: string;
  projectId: string | null;
  startedAt: number;
  steps: OperationStep[];
  cancelled: boolean;
  cancelledAt: number | null;
  finishedApplied: boolean;
  error: { code: string; detail: string } | null;
  // Что показать как итог и что изменить в проекте после успешного завершения.
  result: () => SyncResult | CloneResult;
  apply: () => void;
};

export type DemoWorld = {
  scenarioId: string;
  projects: Map<string, DemoProjectGit>;
  operations: Map<string, DemoOperation>;
  credentials: GitCredential[];
  hosts: GitHost[];
  profile: { name: string; email: string } | null;
  dataDirShared: { provider: string; root: string } | null;
  // Личная настройка приложения «как часто проверять репозитории», секунды.
  defaultFetchIntervalS: number;
  newProject: () => DemoProjectGit;
};

export const emptyProjectGit = (): DemoProjectGit => ({
  remote: null,
  relation: "none",
  ahead: 0,
  behind: 0,
  behindFiles: 0,
  health: "ok",
  lastError: null,
  blocked: null,
  incoming: [],
  outgoing: [],
  operationId: null,
  lastFetchAt: null,
  lastFetchOkAt: null,
  lastSyncAt: null,
  lastSync: null,
  autoFetch: { enabled: true, interval_s: 300 },
  sharedFolder: null,
  sharedAck: false,
  botAuthored: 0,
  ndaFiles: 0,
  lfsPointers: 0,
  overLimit: [],
  conflict: null,
  willConflict: false,
  failWith: null,
});

// --- профиль ----------------------------------------------------------------------

export const profileView = (world: DemoWorld): Profile => {
  const custom = world.profile;
  if (!custom) {
    return {
      name: null,
      email: null,
      effective_name: "HSE Doc Studio",
      effective_email: "studio@hse-doc-studio.local",
      is_default: true,
      commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
    };
  }
  return {
    name: custom.name,
    email: custom.email,
    effective_name: custom.name,
    effective_email: custom.email,
    is_default: false,
    commit_preview: `${custom.name} <${custom.email}>`,
  };
};

// --- доступы ----------------------------------------------------------------------

export const initialCredentials = (authFailed: boolean): GitCredential[] => [
  {
    id: fakeUuid(1),
    kind: "pat",
    label: "GitHub, рабочий токен",
    host: "github.com",
    username: "ivan-smirnov",
    status: authFailed ? "auth_failed" : "ok",
    token_family: "github_pat",
    public_key: null,
    fingerprint_sha256: null,
    created_at: isoAgo(40 * 24 * 60 * MINUTE),
    last_used_at: isoAgo(2 * 60 * MINUTE),
    used_by: [{ project_id: fakeUuid(101), name: "Курсовая работа" }],
  },
  {
    id: fakeUuid(2),
    kind: "ssh_key",
    label: "Ключ для GitLab ВШЭ",
    host: "gitlab.hse.ru",
    username: null,
    status: "unverified",
    token_family: null,
    public_key:
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDemoKeyForVisualReviewOnlyNotARealKey hse-doc-studio",
    fingerprint_sha256: "SHA256:Zk3p0V7m1sJrQxM2n9LdTqEoUy5aBc8HwXf4GiRvN6A",
    created_at: isoAgo(12 * 24 * 60 * MINUTE),
    last_used_at: null,
    used_by: [],
  },
];

export const GITHUB_HOST_KEY = {
  type: "ssh-ed25519",
  fingerprint_sha256: "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",
};

export const initialHosts = (): GitHost[] => [
  {
    host: "github.com",
    port: null,
    key_types: ["ssh-ed25519"],
    fingerprints_sha256: [GITHUB_HOST_KEY.fingerprint_sha256],
    added_at: isoAgo(30 * 24 * 60 * MINUTE),
  },
];

// --- операции ---------------------------------------------------------------------

export const SYNC_STEPS: OperationStep[] = [
  { phase: "snapshot", ms: 700 },
  { phase: "fetch", ms: 1600 },
  { phase: "merge", ms: 900 },
  { phase: "push", ms: 1500 },
];

export const FETCH_ONLY_STEPS: OperationStep[] = [
  { phase: "snapshot", ms: 500 },
  { phase: "fetch", ms: 1200 },
];

export const CLONE_STEPS: OperationStep[] = [
  { phase: "download", ms: 2600 },
  { phase: "verify", ms: 800 },
  { phase: "register", ms: 700 },
];

const stepAt = (
  op: DemoOperation,
  elapsed: number,
): { phase: string; percent: number | null; done: boolean } => {
  let from = 0;
  for (const step of op.steps) {
    if (elapsed < from + step.ms) {
      const inside = (elapsed - from) / step.ms;
      const hasProgress = ["fetch", "push", "download"].includes(step.phase);
      return {
        phase: step.phase,
        percent: hasProgress ? Math.round(inside * 100) : null,
        done: false,
      };
    }
    from += step.ms;
  }
  const last = op.steps[op.steps.length - 1];
  return { phase: last?.phase ?? "queued", percent: null, done: true };
};

const PHASE_MESSAGES: Record<string, string> = {
  fetch: "Receiving objects",
  push: "Writing objects",
  download: "Receiving objects",
};

export const operationTotalMs = (op: DemoOperation): number =>
  op.steps.reduce((sum, step) => sum + step.ms, 0);

export const operationView = (op: DemoOperation): GitOperation => {
  const elapsed = nowMs() - op.startedAt;
  const startedAt = isoAt(op.startedAt);
  if (op.cancelled) {
    return {
      id: op.id,
      kind: op.kind,
      project_id: op.projectId,
      status: "cancelled",
      phase: stepAt(op, (op.cancelledAt ?? nowMs()) - op.startedAt).phase,
      percent: null,
      message: null,
      cancellable: false,
      started_at: startedAt,
      finished_at: isoAt(op.cancelledAt ?? nowMs()),
      result: null,
      error: null,
    };
  }
  const position = stepAt(op, elapsed);
  if (!position.done) {
    return {
      id: op.id,
      kind: op.kind,
      project_id: op.projectId,
      status: "running",
      phase: position.phase,
      percent: position.percent,
      message:
        position.percent === null
          ? null
          : `${PHASE_MESSAGES[position.phase] ?? "Working"}: ${String(position.percent)}%`,
      cancellable: position.phase !== "register",
      started_at: startedAt,
      finished_at: null,
      result: null,
      error: null,
    };
  }
  const finishedAt = isoAt(op.startedAt + operationTotalMs(op));
  if (op.error) {
    return {
      id: op.id,
      kind: op.kind,
      project_id: op.projectId,
      status: "failed",
      phase: position.phase,
      percent: null,
      message: null,
      cancellable: false,
      started_at: startedAt,
      finished_at: finishedAt,
      result: null,
      error: op.error,
    };
  }
  return {
    id: op.id,
    kind: op.kind,
    project_id: op.projectId,
    status: "succeeded",
    phase: position.phase,
    percent: 100,
    message: null,
    cancellable: false,
    started_at: startedAt,
    finished_at: finishedAt,
    result: op.result(),
    error: null,
  };
};

// Завершившиеся операции применяют свои последствия ровно один раз: когда их
// впервые прочитали после окончания (из состояния проекта или самой операции).
export const settleOperations = (world: DemoWorld): void => {
  for (const op of world.operations.values()) {
    if (op.cancelled || op.finishedApplied) continue;
    const view = operationView(op);
    if (view.status === "running") continue;
    op.finishedApplied = true;
    const project = op.projectId ? world.projects.get(op.projectId) : undefined;
    if (project?.operationId === op.id) project.operationId = null;
    if (view.status === "succeeded") op.apply();
    else if (project && op.error) {
      project.lastError = { ...op.error, at: isoAgo(0) };
    }
  }
};

export const startOperation = (
  world: DemoWorld,
  params: Omit<
    DemoOperation,
    "id" | "startedAt" | "cancelled" | "cancelledAt" | "finishedApplied"
  >,
): DemoOperation => {
  const op: DemoOperation = {
    ...params,
    id: nextId("op"),
    startedAt: nowMs(),
    cancelled: false,
    cancelledAt: null,
    finishedApplied: false,
  };
  world.operations.set(op.id, op);
  if (op.projectId) {
    const project = world.projects.get(op.projectId);
    if (project) project.operationId = op.id;
  }
  return op;
};

export const cancelOperation = (world: DemoWorld, op: DemoOperation): void => {
  op.cancelled = true;
  op.cancelledAt = nowMs();
  op.finishedApplied = true;
  const project = op.projectId ? world.projects.get(op.projectId) : undefined;
  if (project?.operationId === op.id) project.operationId = null;
};

// --- итоги синхронизации ----------------------------------------------------------

export const mergeResult = (project: DemoProjectGit): SyncResult => {
  if (project.willConflict) {
    const session = project.conflict ?? buildConflictSession();
    const open = session.session.counts.conflict;
    return {
      outcome: "conflicts",
      pulled_commits: project.behind,
      pushed_commits: 0,
      merge_commit: null,
      files_changed: session.session.counts.total,
      auto: autoMergedFiles(),
      conflicts: { files_total: open, files_open: open },
      warnings: [],
    };
  }
  if (project.relation === "diverged") {
    return {
      outcome: "merged",
      pulled_commits: project.behind,
      pushed_commits: project.ahead,
      merge_commit: fakeSha(`merge-${String(project.behind)}`),
      files_changed: Math.max(project.behindFiles, 4),
      auto: autoMergedFiles(),
      conflicts: null,
      warnings: [{ code: "signatures_stale", paths: ["signatures.json"] }],
    };
  }
  if (project.relation === "ahead" || project.relation === "remote_empty") {
    return {
      outcome: "pushed",
      pulled_commits: 0,
      pushed_commits: project.ahead,
      merge_commit: null,
      files_changed: 0,
      auto: [],
      conflicts: null,
      warnings: [],
    };
  }
  if (project.relation === "behind" || project.relation === "unfetched") {
    return {
      outcome: "fast_forwarded",
      pulled_commits: project.behind,
      pushed_commits: 0,
      merge_commit: null,
      files_changed: project.behindFiles,
      auto: [],
      conflicts: null,
      warnings: [],
    };
  }
  return {
    outcome: "up_to_date",
    pulled_commits: 0,
    pushed_commits: 0,
    merge_commit: null,
    files_changed: 0,
    auto: [],
    conflicts: null,
    warnings: [],
  };
};

const autoMergedFiles = (): SyncResult["auto"] => [
  { path: "references.bib", action: "merged", copy_path: null },
  { path: "chapters/introduction.tex", action: "take_theirs", copy_path: null },
  {
    path: "images/results.png",
    action: "binary_newest",
    copy_path: "images/results.conflict-b71d0e4.png",
  },
];

// Состояние проекта после удачной синхронизации (или решения конфликтов).
export const applySyncSuccess = (
  project: DemoProjectGit,
  result: SyncResult,
): void => {
  project.lastError = null;
  project.health = "ok";
  project.lastFetchAt = isoAgo(0);
  project.lastFetchOkAt = isoAgo(0);
  if (result.outcome === "conflicts") {
    project.conflict ??= buildConflictSession();
    applyDrafts(project.conflict);
    return;
  }
  project.relation = "in_sync";
  project.ahead = 0;
  project.behind = 0;
  project.behindFiles = 0;
  project.incoming = [];
  project.outgoing = [];
  project.conflict = null;
  project.willConflict = false;
  project.lastSyncAt = isoAgo(0);
  project.lastSync = {
    id: nextId("sync"),
    at: isoAgo(0),
    outcome: result.outcome,
    pulled_commits: result.pulled_commits,
    pushed_commits: result.pushed_commits,
  };
};

// --- вспомогательное для сценариев ------------------------------------------------

export const setRelation = (
  project: DemoProjectGit,
  relation: "in_sync" | "ahead" | "behind" | "diverged" | "unfetched",
  ahead = 0,
  behind = 0,
): void => {
  project.relation = relation;
  project.ahead = ahead;
  project.behind = behind;
  project.behindFiles = behind === 0 ? 0 : behind + 3;
  project.incoming = incomingCommits(behind);
  project.outgoing = outgoingCommits(ahead);
};

export const demoRemote = (
  overrides: Partial<GitRemoteInfo> = {},
): GitRemoteInfo => ({
  display_url: "https://github.com/ivan-smirnov/coursework",
  kind: "https",
  host: "github.com",
  provider: "github",
  web_url: "https://github.com/ivan-smirnov/coursework",
  branch: "main",
  local_branch: "master",
  credential: { id: fakeUuid(1), label: "GitHub, рабочий токен", kind: "pat" },
  insecure_http: false,
  ...overrides,
});
