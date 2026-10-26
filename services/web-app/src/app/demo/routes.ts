import type { AxiosResponse } from "axios";
import { apiClient } from "@shared/api";
import {
  demoError,
  demoJson,
  demoNoContent,
  queryString,
  type DemoRequest,
  type DemoResponse,
  type DemoRoute,
} from "@shared/api/demo";
import type {
  FileResolution,
  GitContents,
  GitStatus,
  OperationWarning,
} from "@entities/git-sync";
import { REVEAL_FINGERPRINT, type GitCredential } from "@entities/git-remote";
import { validateProfile, type ProfileIssueCode } from "@entities/profile";
import { DAY, HOUR, MINUTE, fakeSha, fakeUuid, isoAgo, nowMs } from "./clock";
import { ME, TEAMMATES } from "./people";
import {
  applyDrafts,
  conflictBlobText,
  conflictDiff,
  openConflictPaths,
} from "./conflictData";
import {
  CHANGED_HOST_KEY,
  isUrlError,
  parseDemoUrl,
  runDemoProbe,
} from "./probe";
import { createWorld, projectOf } from "./scenarios";
import { useDemoScenarioStore } from "./scenarioStore";
import {
  CLONE_STEPS,
  FETCH_ONLY_STEPS,
  GITHUB_HOST_KEY,
  SYNC_STEPS,
  applySyncSuccess,
  cancelOperation,
  demoRemote,
  mergeResult,
  operationView,
  profileView,
  settleOperations,
  setRelation,
  startOperation,
  type DemoProjectGit,
  type DemoWorld,
} from "./world";

// Мир создаётся при первом обращении и пересоздаётся при смене сценария.
let world: DemoWorld = createWorld(useDemoScenarioStore.getState().scenarioId);

export const getWorld = (): DemoWorld => world;

export const resetWorld = (scenarioId: string): void => {
  world = createWorld(scenarioId);
};

// --- состояние проекта ------------------------------------------------------------

const UI_PRIORITY_ERROR_HEALTH = new Set([
  "error",
  "host_key_changed",
  "remote_missing",
  "branch_missing",
]);

export const deriveUiState = (project: DemoProjectGit): string => {
  if (!project.remote) return "no_remote";
  if (project.operationId) return "syncing";
  if (project.conflict) return "conflicts";
  if (project.blocked) return "blocked";
  if (project.health === "unauthenticated") return "auth_failed";
  if (project.health === "offline") return "offline";
  if (UI_PRIORITY_ERROR_HEALTH.has(project.health)) return "error";
  switch (project.relation) {
    case "unfetched":
      return "unfetched";
    case "remote_empty":
    case "ahead":
      return "ahead";
    case "behind":
      return "behind";
    case "diverged":
      return "diverged";
    default:
      return "up_to_date";
  }
};

const statusOf = (projectId: string): GitStatus => {
  settleOperations(world);
  const project = projectOf(world, projectId);
  const op = project.operationId
    ? world.operations.get(project.operationId)
    : undefined;
  const opView = op ? operationView(op) : null;
  const blocked =
    project.blocked ?? (world.profile ? null : { reason: "profile_required" });
  return {
    connected: project.remote !== null,
    ui_state: deriveUiState({ ...project, blocked }),
    remote: project.remote,
    relation: project.relation,
    ahead: project.ahead,
    behind: project.behind,
    behind_files: project.behindFiles,
    health: project.health,
    last_error: project.lastError,
    blocked,
    profile_ok: world.profile !== null,
    incoming: project.incoming,
    outgoing: project.outgoing,
    operation: opView
      ? {
          id: opView.id,
          kind: opView.kind,
          phase: opView.phase,
          percent: opView.percent ?? null,
          cancellable: opView.cancellable,
          started_at: opView.started_at,
        }
      : null,
    pending: project.conflict
      ? {
          session_id: project.conflict.session.id,
          files_total: project.conflict.session.counts.conflict,
          files_open: project.conflict.session.unresolved,
        }
      : null,
    last_fetch_at: project.lastFetchAt,
    last_fetch_ok_at: project.lastFetchOkAt,
    last_sync_at: project.lastSyncAt,
    last_sync: project.lastSync,
    auto_fetch: {
      enabled: project.autoFetch.enabled,
      interval_s: project.autoFetch.interval_s,
      next_fetch_at:
        project.autoFetch.enabled && project.remote
          ? new Date(
              nowMs() + project.autoFetch.interval_s * 1000,
            ).toISOString()
          : null,
    },
    shared_folder: project.sharedFolder
      ? { ...project.sharedFolder, acknowledged: project.sharedAck }
      : null,
    bot_authored_commits: project.botAuthored,
  };
};

const statusResponse = (projectId: string): DemoResponse =>
  demoJson(statusOf(projectId));

const profileGate = (): DemoResponse | null =>
  world.profile
    ? null
    : demoError(409, "profile_required", "Сначала укажи имя и e-mail автора.");

// Состояния, в которых синхронизация запрещена, и ответ на попытку.
const blockedResponse = (project: DemoProjectGit): DemoResponse | null => {
  const profile = profileGate();
  if (profile) return profile;
  const blocked = project.blocked;
  if (!blocked) return null;
  switch (blocked.reason) {
    case "off_branch":
      return demoError(
        409,
        "off_branch",
        "Проект открыт не на синхронизируемой ветке.",
      );
    case "remote_schema_newer":
      return demoError(
        409,
        "remote_schema_newer",
        "В репозитории проект более новой версии Студии.",
        {
          required_studio: blocked.required_studio ?? "0.4.0",
        },
      );
    case "store_untrusted":
      return demoError(
        409,
        "store_untrusted",
        "История проекта пришла из ненадёжного источника.",
      );
    case "read_only":
      return demoError(
        423,
        "project_read_only",
        "Проект открыт только для чтения.",
      );
    default:
      return demoError(
        409,
        "profile_required",
        "Сначала укажи имя и e-mail автора.",
      );
  }
};

// --- общие помощники ---------------------------------------------------------------

const recordBody = (req: DemoRequest): Record<string, unknown> =>
  req.body !== null && typeof req.body === "object"
    ? (req.body as Record<string, unknown>)
    : {};

const str = (value: unknown): string | null =>
  typeof value === "string" ? value : null;

const FETCH_DEBOUNCE_MS = 15_000;
let lastFetchAt = 0;

const failureOf = (
  project: DemoProjectGit,
): { code: string; detail: string } | null => project.failWith;

const toBlob = (text: string, type: string): Blob => new Blob([text], { type });

const fileOf = (req: DemoRequest, key: string): File | null => {
  const body = req.body;
  if (body instanceof FormData) {
    const value = body.get(key);
    return value instanceof File ? value : null;
  }
  return null;
};

const formString = (req: DemoRequest, key: string): string | null => {
  const body = req.body;
  if (body instanceof FormData) {
    const value = body.get(key);
    return typeof value === "string" ? value : null;
  }
  return null;
};

// --- маршруты проекта --------------------------------------------------------------

const projectRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/projects/:projectId/git",
    handler: (req) => statusResponse(req.params.projectId ?? ""),
  },
  {
    method: "PUT",
    pattern: "/projects/:projectId/git/remote",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      const body = recordBody(req);
      const gate = profileGate();
      if (gate) return gate;
      if (project.remote) {
        return demoError(
          409,
          "remote_exists",
          "У проекта уже есть удалённый репозиторий.",
        );
      }
      const url = str(body.url) ?? "";
      const credentialId = str(body.credential_id);
      const adopt = str(body.adopt);
      const probe = runDemoProbe(world, {
        url,
        credentialId,
        projectId,
        branch: str(body.remote_branch),
      });
      if (probe.status !== 200)
        return { status: probe.status, data: probe.body };
      const result = probe.body as {
        ok: boolean;
        error: { code: string; detail: string; host_keys?: unknown } | null;
        url: {
          display_url: string;
          kind: string;
          host: string | null;
          provider: string;
          owner: string | null;
          repo: string | null;
        };
        relation: string;
        default_branch: string | null;
        required_studio: string | null;
        schema_access: string | null;
      };
      if (!result.ok && result.error) {
        return demoError(502, result.error.code, result.error.detail, {
          host_keys: result.error.host_keys ?? null,
        });
      }
      if (result.relation === "not_studio_project") {
        return demoError(
          409,
          "not_a_studio_project",
          "В репозитории лежит не проект Студии.",
        );
      }
      if (result.relation === "other_project") {
        return demoError(
          409,
          "unrelated_histories",
          "В репозитории другой проект.",
          {
            can_adopt: false,
          },
        );
      }
      if (
        result.relation === "same_project_unrelated_history" &&
        adopt !== "merge_remote"
      ) {
        return demoError(
          409,
          "unrelated_histories",
          "У проектов нет общей истории.",
          {
            can_adopt: true,
          },
        );
      }
      const credential = world.credentials.find((c) => c.id === credentialId);
      const display = result.url.display_url;
      const webUrl =
        result.url.kind === "file" || !result.url.host
          ? null
          : `https://${result.url.host}/${[result.url.owner, result.url.repo].filter(Boolean).join("/")}`;
      project.remote = demoRemote({
        display_url: display,
        kind: result.url.kind,
        host: result.url.host,
        provider: result.url.provider,
        web_url: webUrl,
        branch: str(body.remote_branch) ?? result.default_branch ?? "main",
        local_branch: str(body.branch) ?? "master",
        credential: credential
          ? {
              id: credential.id,
              label: credential.label,
              kind: credential.kind,
            }
          : null,
        insecure_http: body.insecure_http === true,
      });
      project.health = "ok";
      project.lastError = null;
      project.failWith = null;
      project.lastFetchAt = isoAgo(0);
      project.lastFetchOkAt = isoAgo(0);
      if (result.relation === "empty") setRelation(project, "ahead", 5, 0);
      else if (result.relation === "same_project_unrelated_history")
        setRelation(project, "diverged", 4, 3);
      else setRelation(project, "behind", 0, 3);
      if (result.relation === "empty") project.relation = "remote_empty";
      if (result.schema_access === "read_only") {
        project.blocked = {
          reason: "remote_schema_newer",
          required_studio: result.required_studio,
        };
      }
      return statusResponse(projectId);
    },
  },
  {
    method: "DELETE",
    pattern: "/projects/:projectId/git/remote",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      const forget = queryString(req, "forget_credential") === "true";
      const credentialId = project.remote?.credential?.id;
      Object.assign(project, {
        remote: null,
        relation: "none",
        ahead: 0,
        behind: 0,
        behindFiles: 0,
        incoming: [],
        outgoing: [],
        health: "ok",
        lastError: null,
        blocked: null,
        conflict: null,
        operationId: null,
        lastFetchAt: null,
        lastFetchOkAt: null,
        lastSyncAt: null,
        lastSync: null,
        failWith: null,
        willConflict: false,
      } satisfies Partial<DemoProjectGit>);
      if (forget && credentialId) {
        world.credentials = world.credentials.filter(
          (c) => c.id !== credentialId,
        );
      }
      return demoNoContent();
    },
  },
  {
    method: "PATCH",
    pattern: "/projects/:projectId/git/settings",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      const body = recordBody(req);
      if (typeof body.auto_fetch === "boolean")
        project.autoFetch.enabled = body.auto_fetch;
      if (typeof body.interval_s === "number") {
        project.autoFetch.interval_s = Math.max(60, body.interval_s);
      }
      if (body.shared_folder_ack === true) project.sharedAck = true;
      return statusResponse(projectId);
    },
  },
  {
    method: "GET",
    pattern: "/projects/:projectId/git/contents",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      const contents: GitContents = {
        files: 86,
        bytes: 14_800_000,
        commits: 142,
        bot_authored_commits: project.botAuthored,
        signatures: 2,
        nda_files: project.ndaFiles,
        pdf_tracked: true,
        largest: [
          { path: "images/architecture.png", bytes: 3_400_000 },
          { path: "build/coursework.pdf", bytes: 2_100_000 },
          { path: "images/results.png", bytes: 1_800_000 },
          { path: "assets/fonts/PTSerif.ttf", bytes: 980_000 },
          { path: "references.bib", bytes: 120_000 },
        ],
        over_limit: project.overLimit,
        lfs_pointers: project.lfsPointers,
      };
      return demoJson(contents);
    },
  },
  {
    method: "POST",
    pattern: "/projects/:projectId/git/fetch",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      if (!project.remote) return statusResponse(projectId);
      settleOperations(world);
      const fail = failureOf(project);
      if (fail) {
        project.lastFetchAt = isoAgo(0);
        return demoError(502, fail.code, fail.detail);
      }
      if (
        nowMs() - lastFetchAt < FETCH_DEBOUNCE_MS &&
        project.relation !== "unfetched"
      ) {
        return statusResponse(projectId);
      }
      lastFetchAt = nowMs();
      project.lastFetchAt = isoAgo(0);
      project.lastFetchOkAt = isoAgo(0);
      if (project.relation === "unfetched")
        setRelation(project, "behind", 0, project.behind || 3);
      return statusResponse(projectId);
    },
  },
  {
    method: "POST",
    pattern: "/projects/:projectId/git/sync",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      settleOperations(world);
      if (project.operationId) {
        return demoError(409, "sync_busy", "Синхронизация уже идёт.", {
          operation_id: project.operationId,
        });
      }
      const blocked = blockedResponse(project);
      if (blocked) return blocked;
      if (project.conflict) {
        return demoError(
          409,
          "sync_incomplete",
          "Сначала реши конфликты предыдущей синхронизации.",
        );
      }
      const fail = failureOf(project);
      // Итог считаем сейчас: к концу операции проект уже будет «синхронизирован».
      const result = mergeResult(project);
      const op = startOperation(world, {
        kind: "sync",
        projectId,
        steps: fail ? FETCH_ONLY_STEPS : SYNC_STEPS,
        error: fail,
        result: () => result,
        apply: () => {
          applySyncSuccess(project, result);
        },
      });
      return demoJson({ operation_id: op.id }, 202);
    },
  },
  // --- конфликты ---
  {
    method: "GET",
    pattern: "/projects/:projectId/git/conflicts",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      if (!project.conflict) {
        return demoError(404, "no_conflicts", "Открытых конфликтов нет.");
      }
      return demoJson(project.conflict.session);
    },
  },
  {
    method: "GET",
    pattern: "/projects/:projectId/git/conflicts/file",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      const path = queryString(req, "path") ?? "";
      const detail = project.conflict?.details[path];
      if (!detail)
        return demoError(404, "no_conflicts", "Для этого файла конфликта нет.");
      return demoJson(detail);
    },
  },
  {
    method: "GET",
    pattern: "/projects/:projectId/git/conflicts/diff",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      const path = queryString(req, "path") ?? "";
      const view = queryString(req, "view");
      const kind = view === "theirs" || view === "result" ? view : "ours";
      // Итог зависит от сохранённого выбора, как и на настоящем сервере.
      return demoJson(conflictDiff(path, kind, project.conflict?.drafts[path]));
    },
  },
  {
    method: "GET",
    pattern: "/projects/:projectId/git/conflicts/blob",
    handler: (req) => {
      const path = queryString(req, "path") ?? "";
      const side = queryString(req, "side") ?? "ours";
      const isImage = path.endsWith(".png");
      return {
        status: 200,
        data: toBlob(
          conflictBlobText(path, side),
          isImage ? "image/svg+xml" : "text/plain",
        ),
        headers: { "cache-control": "no-store" },
      };
    },
  },
  {
    method: "PUT",
    pattern: "/projects/:projectId/git/conflicts/draft",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      if (!project.conflict)
        return demoError(404, "no_conflicts", "Открытых конфликтов нет.");
      const resolutions = recordBody(req).resolutions as
        Record<string, FileResolution> | undefined;
      project.conflict.drafts = {
        ...project.conflict.drafts,
        ...(resolutions ?? {}),
      };
      applyDrafts(project.conflict);
      return demoNoContent();
    },
  },
  {
    method: "POST",
    pattern: "/projects/:projectId/git/conflicts/resolve",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      const conflict = project.conflict;
      if (!conflict)
        return demoError(404, "no_conflicts", "Открытых конфликтов нет.");
      const body = recordBody(req);
      if (body.fingerprint !== conflict.session.fingerprint) {
        return demoError(
          409,
          "plan_outdated",
          "Чужие изменения обновились: проверь конфликты ещё раз.",
        );
      }
      const given = body.resolutions as
        Record<string, FileResolution> | null | undefined;
      if (given) {
        conflict.drafts = { ...conflict.drafts, ...given };
        applyDrafts(conflict);
      }
      const open = openConflictPaths(conflict);
      if (open.length > 0) {
        return demoError(
          422,
          "unresolved_conflicts",
          "Остались нерешённые конфликты.",
          {
            paths: open,
          },
        );
      }
      const result = {
        ...mergeResult({
          ...project,
          willConflict: false,
          relation: "diverged",
        }),
      };
      const op = startOperation(world, {
        kind: "resolve",
        projectId,
        steps: SYNC_STEPS.slice(2),
        error: null,
        result: () => result,
        apply: () => {
          applySyncSuccess(project, result);
        },
      });
      return demoJson({ operation_id: op.id }, 202);
    },
  },
  {
    method: "DELETE",
    pattern: "/projects/:projectId/git/conflicts",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      project.conflict = null;
      return statusResponse(projectId);
    },
  },
  // --- переносной файл ---
  {
    method: "POST",
    pattern: "/projects/:projectId/git/bundle/export",
    handler: (req) => {
      const password = str(recordBody(req).password);
      const stamp = new Date()
        .toISOString()
        .slice(0, 16)
        .replace(/[-:]/g, "")
        .replace("T", "-");
      const name = `coursework-${stamp}.bundle${password ? ".hseenc" : ""}`;
      return {
        status: 200,
        data: toBlob("# demo bundle\n", "application/octet-stream"),
        headers: {
          "content-disposition": `attachment; filename="${name}"`,
        },
      };
    },
  },
  {
    // Имя файла выбирает исход: "broken" повреждён, "other" от другого проекта,
    // "old" требует более раннего файла, "late" ломается уже при слиянии,
    // ".hseenc" просит пароль ("wrong" не подходит).
    method: "POST",
    pattern: "/projects/:projectId/git/bundle/import",
    handler: (req) => {
      const projectId = req.params.projectId ?? "";
      const project = projectOf(world, projectId);
      const file = fileOf(req, "file");
      const password = formString(req, "password");
      if (!file || file.name.toLowerCase().includes("broken")) {
        return demoError(
          400,
          "bundle_invalid",
          "Файл повреждён или не является переносным файлом проекта.",
        );
      }
      if (file.name.endsWith(".hseenc")) {
        if (!password)
          return demoError(
            400,
            "bundle_password_required",
            "Файл зашифрован: нужен пароль.",
          );
        if (password === "wrong")
          return demoError(400, "bundle_password_wrong", "Пароль не подошёл.");
      }
      const name = file.name.toLowerCase();
      if (name.includes("other")) {
        return demoError(
          409,
          "unrelated_histories",
          "История файла не связана с историей проекта.",
          { can_adopt: false },
        );
      }
      if (name.includes("old")) {
        return demoError(
          400,
          "bundle_prerequisites_missing",
          "В файле нет истории, на которой он построен.",
        );
      }
      if (project.operationId) {
        return demoError(409, "sync_busy", "Синхронизация уже идёт.", {
          operation_id: project.operationId,
        });
      }
      const late = name.includes("late");
      const op = startOperation(world, {
        kind: "bundle_import",
        projectId,
        steps: [
          { phase: "snapshot", ms: 600 },
          { phase: "verify", ms: 900 },
          { phase: "merge", ms: 1200 },
        ],
        error: late
          ? {
              code: "bundle_prerequisites_missing",
              detail: "В файле нет истории, на которой он построен.",
            }
          : null,
        result: () =>
          mergeResult({
            ...project,
            relation: "diverged",
            behind: 2,
            ahead: 0,
            behindFiles: 5,
          }),
        apply: () => {
          const result = mergeResult({
            ...project,
            relation: "diverged",
            behind: 2,
            ahead: 0,
            behindFiles: 5,
          });
          if (result.outcome === "conflicts") applySyncSuccess(project, result);
        },
      });
      return demoJson({ operation_id: op.id }, 202);
    },
  },
  // --- сборка в CI ---
  {
    method: "POST",
    pattern: "/projects/:projectId/git/ci/preview",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      return demoJson(ciPreview(project, recordBody(req)));
    },
  },
  {
    method: "POST",
    pattern: "/projects/:projectId/git/ci/write",
    handler: (req) => {
      const project = projectOf(world, req.params.projectId ?? "");
      const body = recordBody(req);
      const preview = ciPreview(project, body);
      // Без подтверждения отличающийся файл не трогаем.
      const written = preview.files.filter(
        (file) => body.overwrite === true || !file.exists || file.same,
      );
      for (const file of written) {
        project.ciFiles[file.path] = file.content;
      }
      return demoJson({ written: written.map((file) => file.path) });
    },
  },
];

const CI_IMAGE = "ghcr.io/hse-doc-studio/builder:0.2.0";

const stringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

const ciPreview = (project: DemoProjectGit, body: Record<string, unknown>) => {
  const provider = body.provider === "gitlab" ? "gitlab" : "github";
  const docs = stringList(body.docs);
  const triggers = stringList(body.triggers);
  const release = body.publish === "release";
  const customImage = str(body.image);
  const image =
    customImage !== null && customImage !== "" ? customImage : CI_IMAGE;
  const path =
    provider === "gitlab"
      ? ".gitlab-ci.yml"
      : ".github/workflows/hse-studio-build.yml";
  const command =
    docs.length > 0
      ? `hse-doc-studio build ${docs.map((doc) => `--doc ${doc}`).join(" ")}`
      : "hse-doc-studio build --all";
  const lines =
    provider === "gitlab"
      ? [
          "build-documents:",
          `  image: ${image}`,
          "  script:",
          `    - ${command}`,
          "  artifacts:",
          "    paths:",
          "      - build/*.pdf",
          ...(triggers.length > 0
            ? [
                "  rules:",
                ...(triggers.includes("push")
                  ? ["    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"]
                  : []),
                ...(triggers.includes("tag")
                  ? ["    - if: $CI_COMMIT_TAG"]
                  : []),
                ...(triggers.includes("manual") ? ["    - when: manual"] : []),
              ]
            : []),
          ...(release
            ? [
                "release-documents:",
                "  stage: deploy",
                "  rules:",
                "    - if: $CI_COMMIT_TAG",
                "  script:",
                "    - echo Публикуем PDF в релиз",
              ]
            : []),
          "",
        ]
      : [
          "name: Сборка документов",
          "on:",
          ...(triggers.includes("push") || triggers.includes("tag")
            ? [
                "  push:",
                ...(triggers.includes("push") ? ["    branches: [main]"] : []),
                ...(triggers.includes("tag") ? ["    tags: ['v*']"] : []),
              ]
            : []),
          ...(triggers.includes("manual") ? ["  workflow_dispatch:"] : []),
          "jobs:",
          "  build:",
          "    runs-on: ubuntu-latest",
          `    container: ${image}`,
          "    steps:",
          "      - uses: actions/checkout@v4",
          `      - run: ${command}`,
          release
            ? "      - uses: softprops/action-gh-release@v2"
            : "      - uses: actions/upload-artifact@v4",
          "        with:",
          ...(release ? [] : ["          name: documents"]),
          release
            ? "          files: build/*.pdf"
            : "          path: build/*.pdf",
          "",
        ];
  const content = lines.join("\n");
  // В демо у GitLab файл уже есть и отличается: так виден запрос на замену.
  const existing =
    project.ciFiles[path] ??
    (provider === "gitlab" ? "# старый файл сборки\n" : null);
  return {
    files: [
      {
        path,
        content,
        exists: existing !== null,
        same: existing === content,
      },
    ],
    command,
    notes: [
      release
        ? "Релиз создаётся для тегов вида v*, нужен токен с правом записи."
        : "PDF сохраняются как артефакты сборки и хранятся ограниченное время.",
    ],
  };
};

// --- глобальные маршруты ----------------------------------------------------------

const sshFingerprint = (seed: string): string =>
  `SHA256:${fakeSha(seed).slice(0, 43)}`;

// Наружу отдаётся только известный префикс токена, никогда не его часть дальше.
const TOKEN_FAMILIES: [string, string][] = [
  ["github_pat_", "github_pat"],
  ["ghp_", "ghp"],
  ["glpat-", "glpat"],
];

const tokenFamily = (token: string): string | null =>
  TOKEN_FAMILIES.find(([prefix]) => token.startsWith(prefix))?.[1] ?? null;

const credentialPublic = (credential: GitCredential): GitCredential =>
  credential;

// Настройки приложения: настоящие, если бэкенд отвечает, иначе заглушка. Подменяем
// только интервал фоновой проверки, чтобы раздел «Доступ к репозиториям» работал.
const FALLBACK_APP_SETTINGS = {
  theme: "system",
  interface_language: "ru",
  default_engine: "xelatex",
  latex_passes: 2,
  max_concurrent_compiles: 2,
  latex_flags: null,
  compile_image: null,
  default_ai_provider_id: null,
  default_ai_model: null,
  agent_auto_approve_writes: false,
  auto_update: true,
  disk_usage_warn_gb: 5,
};

// Последний ответ настоящего бэкенда: по нему отвечаем на сохранение, которое
// касается только демо-настройки, чтобы не подменить язык и тему заглушкой.
let lastAppSettings: Record<string, unknown> = FALLBACK_APP_SETTINGS;

const appSettings = async (
  req: DemoRequest,
  forward = true,
): Promise<Record<string, unknown>> => {
  if (forward) {
    try {
      const response = await req.forward();
      if (response.data !== null && typeof response.data === "object") {
        lastAppSettings = response.data as Record<string, unknown>;
      }
    } catch {
      // Настоящего бэкенда нет: остаются прежние значения.
    }
  }
  return {
    ...lastAppSettings,
    git_fetch_interval_s: world.defaultFetchIntervalS,
  };
};

const DEMO_HOME = "/Users/demo";

const globalRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/git/credentials",
    handler: () => demoJson(world.credentials.map(credentialPublic)),
  },
  {
    method: "POST",
    pattern: "/git/credentials",
    handler: (req) => {
      const body = recordBody(req);
      const kind = body.kind;
      const label = (str(body.label) ?? "").trim();
      const host = (str(body.host) ?? "").trim().toLowerCase();
      if (
        label === "" ||
        host === "" ||
        (kind !== "pat" && kind !== "ssh_key")
      ) {
        return demoError(
          422,
          "credential_invalid",
          "Данные доступа заполнены неверно.",
        );
      }
      const id = fakeUuid(
        1000 + world.credentials.length + Math.floor(nowMs() % 1000),
      );
      let credential: GitCredential;
      if (kind === "pat") {
        const token = str(body.token) ?? "";
        if (token.trim() === "") {
          return demoError(422, "credential_invalid", "Токен не заполнен.");
        }
        credential = {
          id,
          kind,
          label,
          host,
          username: str(body.username),
          status: "unverified",
          token_family: tokenFamily(token),
          public_key: null,
          fingerprint_sha256: null,
          created_at: isoAgo(0),
          last_used_at: null,
          used_by: [],
        };
      } else {
        credential = {
          id,
          kind,
          label,
          host,
          username: null,
          status: "unverified",
          token_family: null,
          public_key: `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI${fakeSha(id).slice(0, 36)} hse-doc-studio`,
          fingerprint_sha256: sshFingerprint(id),
          created_at: isoAgo(0),
          last_used_at: null,
          used_by: [],
        };
      }
      world.credentials = [...world.credentials, credential];
      return demoJson(credential, 201);
    },
  },
  {
    method: "PATCH",
    pattern: "/git/credentials/:id",
    handler: (req) => {
      const body = recordBody(req);
      const index = world.credentials.findIndex((c) => c.id === req.params.id);
      const current = world.credentials[index];
      if (!current)
        return demoError(404, "credential_invalid", "Доступ не найден.");
      const token = str(body.token);
      const updated: GitCredential = {
        ...current,
        label: str(body.label) ?? current.label,
        username:
          body.username === undefined ? current.username : str(body.username),
        // Новый токен сбрасывает прежний итог проверки.
        status: token && token.trim() !== "" ? "unverified" : current.status,
      };
      world.credentials[index] = updated;
      // Новый токен снимает отказ входа у проектов, которые им пользуются.
      if (token && token.trim() !== "") {
        for (const project of world.projects.values()) {
          if (project.remote?.credential?.id !== updated.id) continue;
          if (project.failWith?.code === "auth_failed") project.failWith = null;
          if (project.health === "unauthenticated") {
            project.health = "ok";
            project.lastError = null;
          }
        }
      }
      return demoJson(updated);
    },
  },
  {
    method: "DELETE",
    pattern: "/git/credentials/:id",
    handler: (req) => {
      const credential = world.credentials.find((c) => c.id === req.params.id);
      if (!credential) return demoNoContent();
      const force = queryString(req, "force") === "true";
      if (credential.used_by.length > 0 && !force) {
        return demoError(
          409,
          "credential_in_use",
          "Доступ используется в проектах.",
          {
            projects: credential.used_by,
          },
        );
      }
      world.credentials = world.credentials.filter(
        (c) => c.id !== credential.id,
      );
      return demoNoContent();
    },
  },
  {
    method: "GET",
    pattern: "/git/hosts",
    handler: () => demoJson(world.hosts),
  },
  {
    method: "POST",
    pattern: "/git/hosts/trust",
    handler: (req) => {
      const body = recordBody(req);
      const host = (str(body.host) ?? "").toLowerCase();
      const known = world.hosts.find((h) => h.host === host);
      if (known && body.replace !== true) {
        return demoError(409, "host_key_changed", "Ключ сервера изменился.", {
          expected: known.fingerprints_sha256[0] ?? "",
          // Запрос-заглушка узнаёт ключ, который сервер предъявляет сейчас.
          actual:
            body.fingerprint_sha256 === REVEAL_FINGERPRINT
              ? CHANGED_HOST_KEY.fingerprint_sha256
              : (str(body.fingerprint_sha256) ?? ""),
        });
      }
      if (known && body.confirm_host !== host) {
        return demoError(
          409,
          "host_key_changed",
          "Для замены ключа введи имя сервера.",
          {
            expected: known.fingerprints_sha256[0] ?? "",
            actual: str(body.fingerprint_sha256) ?? "",
          },
        );
      }
      const entry = {
        host,
        port: typeof body.port === "number" ? body.port : null,
        key_types: ["ssh-ed25519"],
        fingerprints_sha256: [
          str(body.fingerprint_sha256) ?? GITHUB_HOST_KEY.fingerprint_sha256,
        ],
        added_at: isoAgo(0),
      };
      world.hosts = [...world.hosts.filter((h) => h.host !== host), entry];
      return demoNoContent();
    },
  },
  {
    method: "DELETE",
    pattern: "/git/hosts",
    handler: (req) => {
      const host = queryString(req, "host");
      world.hosts = world.hosts.filter((h) => h.host !== host);
      return demoNoContent();
    },
  },
  {
    method: "GET",
    pattern: "/git/secrets/status",
    handler: () =>
      demoJson({
        ok: true,
        source: "file",
        permissions_enforced: true,
        credentials_total: world.credentials.length,
        credentials_unreadable: 0,
        data_dir_shared_folder: world.dataDirShared,
      }),
  },
  {
    method: "GET",
    pattern: "/git/shared-folder",
    handler: (req) => {
      const folder = queryString(req, "folder") ?? "";
      const lower = folder.toLowerCase();
      const providers: [string, string][] = [
        ["yandex", "yandex_disk"],
        ["dropbox", "dropbox"],
        ["onedrive", "onedrive"],
        ["icloud", "icloud"],
        ["google drive", "google_drive"],
        ["nextcloud", "nextcloud"],
        ["syncthing", "syncthing"],
      ];
      const found = providers.find(([word]) => lower.includes(word));
      return demoJson({
        detected: found !== undefined,
        provider: found?.[1] ?? null,
        root: found ? folder.split("/").slice(0, 4).join("/") : null,
        evidence: found ? [`Путь содержит «${found[0]}»`] : [],
      });
    },
  },
  {
    method: "POST",
    pattern: "/git/remote/probe",
    handler: (req) => {
      const body = recordBody(req);
      const result = runDemoProbe(world, {
        url: str(body.url) ?? "",
        credentialId: str(body.credential_id),
        projectId: str(body.project_id),
        branch: str(body.branch),
      });
      if (result.status !== 200)
        return { status: result.status, data: result.body };
      return demoJson(result.body);
    },
  },
  {
    method: "GET",
    pattern: "/git/clone/defaults",
    handler: (req) => {
      const name = (queryString(req, "name") ?? "").trim();
      const slug = (name || "project")
        .toLowerCase()
        .replace(/[^a-z0-9а-яё]+/gi, "-")
        .replace(/^-|-$/g, "");
      return demoJson({ folder: `~/HSE Doc Studio/${slug || "project"}` });
    },
  },
  {
    method: "POST",
    pattern: "/git/clone",
    handler: (req) => {
      const body = recordBody(req);
      const url = str(body.url) ?? "";
      const folder = str(body.folder) ?? "";
      const parsed = parseDemoUrl(url);
      if (isUrlError(parsed)) return { status: 400, data: parsed };
      if (folder.toLowerCase().includes("busy")) {
        return demoError(409, "folder_not_empty", "Папка не пуста.");
      }
      if (folder.toLowerCase().includes("exists")) {
        return demoError(
          409,
          "project_exists",
          "Проект из этой папки уже открыт.",
        );
      }
      const probe = runDemoProbe(world, {
        url,
        credentialId: str(body.credential_id),
        projectId: null,
      });
      const outcome = probe.body as {
        ok?: boolean;
        error?: { code: string; detail: string } | null;
        relation?: string;
      };
      const failure =
        outcome.ok === false && outcome.error ? outcome.error : null;
      const projectId = fakeUuid(5000 + Math.floor(nowMs() % 1000));
      const warnings: OperationWarning[] = [];
      const op = startOperation(world, {
        kind: "clone",
        projectId: null,
        steps: failure ? CLONE_STEPS.slice(0, 1) : CLONE_STEPS,
        error: failure ? { code: failure.code, detail: failure.detail } : null,
        result: () => ({
          project_id: projectId,
          folder,
          access: "full",
          required_studio: null,
          warnings,
        }),
        apply: () => undefined,
      });
      return demoJson({ operation_id: op.id }, 202);
    },
  },
  {
    method: "POST",
    pattern: "/git/clone/bundle",
    handler: (req) => {
      const file = fileOf(req, "file");
      const folder = formString(req, "folder") ?? "";
      const password = formString(req, "password");
      if (!file || file.name.toLowerCase().includes("broken")) {
        return demoError(
          400,
          "bundle_invalid",
          "Файл повреждён или не является переносным файлом проекта.",
        );
      }
      if (file.name.endsWith(".hseenc")) {
        if (!password)
          return demoError(
            400,
            "bundle_password_required",
            "Файл зашифрован: нужен пароль.",
          );
        if (password === "wrong")
          return demoError(400, "bundle_password_wrong", "Пароль не подошёл.");
      }
      const projectId = fakeUuid(6000 + Math.floor(nowMs() % 1000));
      const op = startOperation(world, {
        kind: "clone",
        projectId: null,
        steps: CLONE_STEPS,
        error: null,
        result: () => ({
          project_id: projectId,
          folder,
          access: "full",
          required_studio: null,
          warnings: [],
        }),
        apply: () => undefined,
      });
      return demoJson({ operation_id: op.id }, 202);
    },
  },
  {
    method: "GET",
    pattern: "/git/operations/:id",
    handler: (req) => {
      settleOperations(world);
      const op = world.operations.get(req.params.id ?? "");
      if (!op)
        return demoError(404, "not_found_or_no_access", "Операция не найдена.");
      return demoJson(operationView(op));
    },
  },
  {
    method: "POST",
    pattern: "/git/operations/:id/cancel",
    handler: (req) => {
      settleOperations(world);
      const op = world.operations.get(req.params.id ?? "");
      if (!op)
        return demoError(404, "not_found_or_no_access", "Операция не найдена.");
      const view = operationView(op);
      if (!view.cancellable) {
        return demoError(
          409,
          "operation_not_cancellable",
          "Операцию уже нельзя отменить.",
        );
      }
      cancelOperation(world, op);
      return demoJson(operationView(op));
    },
  },
  // --- выбор папки для клонирования: настоящий ответ, а без бэкенда заглушка ---
  {
    method: "GET",
    pattern: "/fs/inspect",
    handler: async (req) => {
      try {
        const response = await req.forward();
        return demoJson(response.data);
      } catch {
        const path = queryString(req, "path") ?? "";
        const lower = path.toLowerCase();
        // Слова в пути выбирают исход: exists (там уже проект), busy (папка с файлами).
        const hasProject = lower.includes("exists");
        const exists = hasProject || lower.includes("busy");
        return demoJson({
          path,
          exists,
          is_dir: !lower.endsWith(".txt"),
          has_project: hasProject,
          project: hasProject
            ? {
                id: fakeUuid(7000),
                name: "Курсовая работа",
                pack_id: "hse-cs-sse",
                template_id: "coursework",
                version: "1.2.0",
                engine: "xelatex",
              }
            : null,
        });
      }
    },
  },
  {
    method: "GET",
    pattern: "/fs/browse",
    handler: async (req) => {
      try {
        const response = await req.forward();
        return demoJson(response.data);
      } catch {
        const path = queryString(req, "path") ?? DEMO_HOME;
        const entry = (name: string) => ({
          name,
          path: `${path.replace(/\/$/, "")}/${name}`,
          is_dir: true,
          is_hidden: false,
        });
        return demoJson({
          path,
          parent: path === DEMO_HOME ? null : DEMO_HOME,
          is_root: path === DEMO_HOME,
          entries: [
            entry("HSE Doc Studio"),
            entry("Документы"),
            entry("Учёба"),
          ],
        });
      }
    },
  },
  // --- настройки приложения: только интервал фоновой проверки ---
  {
    method: "GET",
    pattern: "/settings",
    handler: async (req) => demoJson(await appSettings(req)),
  },
  {
    method: "PUT",
    pattern: "/settings",
    handler: async (req) => {
      const { git_fetch_interval_s: interval, ...rest } = recordBody(req);
      if (typeof interval === "number") world.defaultFetchIntervalS = interval;
      // Остальные настройки принадлежат настоящему бэкенду, если он есть.
      return demoJson(await appSettings(req, Object.keys(rest).length > 0));
    },
  },
  // --- профиль автора ---
  {
    method: "GET",
    pattern: "/profile",
    handler: () => demoJson(profileView(world)),
  },
  {
    method: "PUT",
    pattern: "/profile",
    handler: (req) => {
      const body = recordBody(req);
      const check = validateProfile({
        name: str(body.name) ?? "",
        email: str(body.email) ?? "",
      });
      if (!check.isValid) {
        const issues = (["name", "email"] as const).flatMap((field) => {
          const code = check.issues[field];
          return code
            ? [{ loc: ["body", field], code, msg: PROFILE_ISSUE_TEXT[code] }]
            : [];
        });
        return { status: 422, data: { detail: issues } };
      }
      const { name, email } = check;
      world.profile = { name, email };
      clearProfileBlock();
      return demoJson(profileView(world));
    },
  },
  {
    method: "DELETE",
    pattern: "/profile",
    handler: () => {
      world.profile = null;
      return demoJson(profileView(world));
    },
  },
];

const PROFILE_ISSUE_TEXT: Record<ProfileIssueCode, string> = {
  name_required: "Укажи имя: так тебя увидят коллеги.",
  name_too_long: "Слишком длинное имя: не больше 128 символов.",
  name_invalid: "В имени нельзя использовать < и >.",
  email_required: "Укажи e-mail.",
  email_too_long: "Слишком длинный адрес: не больше 254 символов.",
  email_invalid: "Укажи адрес вида name@example.com.",
};

const clearProfileBlock = (): void => {
  for (const project of world.projects.values()) {
    if (project.blocked?.reason === "profile_required") project.blocked = null;
  }
};

// --- история версий: настоящий ответ дополняем метками синхронизации --------------

type RawCommit = {
  id: string;
  kind: string;
  author: string;
  message?: string;
  parents?: unknown[];
  author_email?: string | null;
  sync?: string | null;
  [key: string]: unknown;
};

// Почта автора: известных людей берём из демо-данных, чтобы «Только мои» и
// аватары совпадали с профилем, остальным придумываем адрес.
const emailOf = (name: string): string =>
  [ME, ...TEAMMATES].find((person) => person.name === name)?.email ??
  `${name.toLowerCase().replace(/\s+/g, ".")}@edu.hse.ru`;

type SyntheticSeed = [string, string, string, number, number];

// Своя история без настоящего бэкенда: чтобы страницу истории можно было
// пролистать и с фильтрами, и с метками отправки, и со слиянием.
const syntheticHistory = (projectId: string): RawCommit[] => {
  const project = projectOf(world, projectId);
  const own = project.outgoing.map((commit) => ({
    id: commit.id,
    short_id: commit.short_id,
    kind: commit.kind,
    message: commit.message,
    author: commit.author,
    created_at: commit.created_at,
    parents: [fakeSha(`parent-${commit.id}`)],
    refs: [],
    doc_id: null,
    stats: { files: 1, insertions: 6, deletions: 2 },
  }));
  const older: SyntheticSeed[] = [
    ["Слияние с репозиторием", "sync", "Иван Смирнов", 2 * DAY + HOUR, 3],
    [
      "Добавлена глава про требования",
      "manual",
      "Анна Петрова",
      2 * DAY + 3 * HOUR,
      4,
    ],
    ["Сборка документа", "compile", "Иван Смирнов", 3 * DAY, 1],
    ["Правки введения", "edit", "Иван Смирнов", 3 * DAY + 2 * HOUR, 2],
    [
      "Обновлён шаблон до версии 1.2",
      "template_update",
      "Иван Смирнов",
      4 * DAY,
      5,
    ],
    ["Список литературы", "edit", "Дмитрий Орлов", 5 * DAY, 1],
    ["Версия для руководителя", "manual", "Иван Смирнов", 6 * DAY, 7],
    ["Проект создан", "init", "Иван Смирнов", 9 * DAY, 12],
  ];
  const rest = older.map(([message, kind, author, ago, files], index) => {
    const id = fakeSha(`history-${String(index)}`);
    return {
      id,
      short_id: id.slice(0, 7),
      kind,
      message,
      author,
      created_at: isoAgo(ago + 30 * MINUTE),
      parents:
        kind === "sync"
          ? [fakeSha("merge-a"), fakeSha("merge-b")]
          : [fakeSha(`parent-${id}`)],
      refs: [],
      doc_id: null,
      stats: { files, insertions: files * 5, deletions: files },
    };
  });
  return [...own, ...rest];
};

const inWindow = (
  createdAt: string,
  since: string | null,
  until: string | null,
): boolean => {
  const time = Date.parse(createdAt);
  if (since && time < Date.parse(since)) return false;
  if (until && time > Date.parse(until)) return false;
  return true;
};

const enrichCommits = (
  commits: RawCommit[],
  projectId: string,
): RawCommit[] => {
  const project = projectOf(world, projectId);
  const connected = project.remote !== null;
  const total = commits.length;
  const ahead = Math.min(project.ahead, total);
  return commits.map((commit, index) => ({
    ...commit,
    author_email: emailOf(commit.author),
    is_merge: Array.isArray(commit.parents) && commit.parents.length > 1,
    // Верхние ahead версий ещё не ушли в репозиторий, остальные уже там.
    sync: connected ? (index < ahead ? "unpushed" : "pushed") : null,
  }));
};

const incomingAsHistory = (projectId: string): RawCommit[] => {
  const project = projectOf(world, projectId);
  return project.incoming.map((commit) => ({
    id: commit.id,
    short_id: commit.short_id,
    kind: commit.kind,
    message: commit.message,
    author: commit.author,
    author_email: commit.author_email ?? null,
    created_at: commit.created_at,
    parents: [],
    refs: [],
    doc_id: null,
    stats: null,
    is_merge: false,
    sync: "incoming",
  }));
};

const historyRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/projects/:projectId/vcs/history",
    handler: async (req) => {
      const projectId = req.params.projectId ?? "";
      let response: AxiosResponse;
      let backendDown = false;
      try {
        response = await req.forward();
      } catch {
        // Настоящего бэкенда нет: история целиком из демо.
        backendDown = true;
        response = { data: [] } as AxiosResponse;
      }
      const real = backendDown
        ? syntheticHistory(projectId)
        : Array.isArray(response.data)
          ? (response.data as RawCommit[])
          : [];
      const project = projectOf(world, projectId);
      const all = project.remote
        ? [...incomingAsHistory(projectId), ...enrichCommits(real, projectId)]
        : enrichCommits(real, projectId);
      const kinds = ([] as string[]).concat(req.query.kind ?? []);
      const email = queryString(req, "author_email");
      const text = (queryString(req, "q") ?? "").toLowerCase();
      const sync = queryString(req, "sync");
      const since = queryString(req, "since");
      const until = queryString(req, "until");
      const filtered = all.filter((commit) => {
        if (
          typeof commit.created_at === "string" &&
          !inWindow(commit.created_at, since, until)
        )
          return false;
        if (kinds.length > 0 && !kinds.includes(commit.kind)) return false;
        if (email && commit.author_email !== email) return false;
        if (text && !(commit.message ?? "").toLowerCase().includes(text))
          return false;
        if (sync === "unpushed" && commit.sync !== "unpushed") return false;
        if (sync === "incoming" && commit.sync !== "incoming") return false;
        return true;
      });
      const offset = Number(queryString(req, "offset") ?? "0") || 0;
      const limit = Number(queryString(req, "limit") ?? "100") || 100;
      return demoJson(filtered.slice(offset, offset + limit));
    },
  },
  {
    method: "GET",
    pattern: "/projects/:projectId/vcs/history/facets",
    handler: async (req) => {
      const projectId = req.params.projectId ?? "";
      let commits: RawCommit[] = [];
      try {
        // Через общий клиент: запрос попадёт в обработчик истории выше.
        const response = await apiClient.get(
          `/projects/${projectId}/vcs/history`,
          {
            params: { limit: 500 },
            silentError: true,
          },
        );
        if (Array.isArray(response.data))
          commits = response.data as RawCommit[];
      } catch {
        commits = [];
      }
      const kinds: Record<string, number> = {};
      const authors = new Map<
        string,
        { name: string; email: string | null; count: number }
      >();
      for (const commit of [
        ...incomingAsHistory(projectId),
        ...enrichCommits(commits, projectId),
      ]) {
        kinds[commit.kind] = (kinds[commit.kind] ?? 0) + 1;
        const email = (commit.author_email as string | null) ?? null;
        const key = email ?? commit.author;
        const entry = authors.get(key) ?? {
          name: commit.author,
          email,
          count: 0,
        };
        entry.count += 1;
        authors.set(key, entry);
      }
      return demoJson({ kinds, authors: [...authors.values()] });
    },
  },
];

export const gitDemoRoutes: DemoRoute[] = [
  ...projectRoutes,
  ...globalRoutes,
  ...historyRoutes,
];
