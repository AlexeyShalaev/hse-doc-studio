import { MINUTE, isoAgo } from "./clock";
import { buildConflictSession } from "./conflictData";
import {
  CLONE_STEPS,
  SYNC_STEPS,
  applySyncSuccess,
  demoRemote,
  emptyProjectGit,
  initialCredentials,
  initialHosts,
  mergeResult,
  setRelation,
  startOperation,
  type DemoProjectGit,
  type DemoWorld,
} from "./world";
import { ME } from "./people";

// Сценарий задаёт, как выглядит синхронизация у любого проекта сразу после
// запуска. Дальше состояние живёт по правилам обработчиков: можно подключить
// репозиторий, запустить синхронизацию, решить конфликты.

export type DemoScenarioId =
  | "not_connected"
  | "connect_warnings"
  | "connect_large_files"
  | "connect_no_profile"
  | "unfetched"
  | "up_to_date"
  | "ahead"
  | "behind"
  | "diverged"
  | "diverged_conflicts"
  | "syncing"
  | "conflicts"
  | "auth_failed"
  | "offline"
  | "error"
  | "schema_newer"
  | "off_branch"
  | "read_only"
  | "no_profile"
  | "shared_folder";

export type DemoScenario = {
  id: DemoScenarioId;
  // Группа в списке выбора: подключение, состояния, проблемы.
  group: "connect" | "state" | "problem";
  // Настраивает состояние проекта; world нужен тем, кто запускает операцию.
  setup: (project: DemoProjectGit, world: DemoWorld, projectId: string) => void;
  // Настраивает общий мир: профиль, доступы, папка данных.
  configureWorld?: (world: DemoWorld) => void;
};

const connected = (project: DemoProjectGit): void => {
  project.remote = demoRemote();
  project.lastFetchAt = isoAgo(4 * MINUTE);
  project.lastFetchOkAt = isoAgo(4 * MINUTE);
  project.lastSyncAt = isoAgo(3 * 60 * MINUTE);
  project.lastSync = {
    id: "sync-seed",
    at: isoAgo(3 * 60 * MINUTE),
    outcome: "merged",
    pulled_commits: 2,
    pushed_commits: 3,
  };
};

export const SCENARIOS: DemoScenario[] = [
  {
    id: "not_connected",
    group: "connect",
    setup: (project) => {
      project.botAuthored = 14;
    },
  },
  {
    // Всё, о чём окно подключения предупреждает, но что не мешает подключить.
    id: "connect_warnings",
    group: "connect",
    setup: (project) => {
      project.botAuthored = 14;
      project.ndaFiles = 2;
      project.lfsPointers = 3;
      project.sharedFolder = {
        provider: "yandex_disk",
        root: "/Users/ivan/Yandex.Disk",
      };
    },
  },
  {
    // Слишком крупные файлы в истории: окно не даёт перейти дальше.
    id: "connect_large_files",
    group: "connect",
    setup: (project) => {
      const MB = 1024 * 1024;
      project.overLimit = [
        {
          path: "video/defense-rehearsal.mov",
          bytes: 187 * MB,
          limit: 95 * MB,
        },
        { path: "data/survey-raw.csv", bytes: 112 * MB, limit: 95 * MB },
      ];
    },
  },
  {
    // Автор версий ещё не указан: окно начинается с «Представься».
    id: "connect_no_profile",
    group: "connect",
    setup: () => undefined,
    configureWorld: (world) => {
      world.profile = null;
    },
  },
  {
    id: "unfetched",
    group: "connect",
    setup: (project) => {
      connected(project);
      project.lastFetchAt = null;
      project.lastFetchOkAt = null;
      project.lastSync = null;
      project.lastSyncAt = null;
      setRelation(project, "unfetched", 0, 3);
    },
  },
  {
    id: "up_to_date",
    group: "state",
    setup: (project) => {
      connected(project);
      setRelation(project, "in_sync");
    },
  },
  {
    id: "ahead",
    group: "state",
    setup: (project) => {
      connected(project);
      setRelation(project, "ahead", 4, 0);
    },
  },
  {
    id: "behind",
    group: "state",
    setup: (project) => {
      connected(project);
      setRelation(project, "behind", 0, 3);
    },
  },
  {
    id: "diverged",
    group: "state",
    setup: (project) => {
      connected(project);
      setRelation(project, "diverged", 3, 2);
    },
  },
  {
    id: "diverged_conflicts",
    group: "state",
    setup: (project) => {
      connected(project);
      setRelation(project, "diverged", 3, 2);
      project.willConflict = true;
    },
  },
  {
    id: "syncing",
    group: "state",
    setup: (project, world, projectId) => {
      connected(project);
      setRelation(project, "diverged", 3, 2);
      // Длинная операция, чтобы состояние можно было рассмотреть и отменить.
      const result = mergeResult(project);
      startOperation(world, {
        kind: "sync",
        projectId,
        steps: [
          { phase: "snapshot", ms: 4_000 },
          { phase: "fetch", ms: 120_000 },
          ...SYNC_STEPS.slice(2),
        ],
        error: null,
        result: () => result,
        apply: () => {
          applySyncSuccess(project, result);
        },
      });
    },
  },
  {
    id: "conflicts",
    group: "state",
    setup: (project) => {
      connected(project);
      setRelation(project, "diverged", 3, 2);
      project.conflict = buildConflictSession();
      project.willConflict = true;
    },
  },
  {
    id: "auth_failed",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "behind", 0, 2);
      project.health = "unauthenticated";
      project.lastError = {
        code: "auth_failed",
        detail: "Сервер отклонил токен: он отозван или просрочен.",
        at: isoAgo(2 * MINUTE),
      };
      project.failWith = {
        code: "auth_failed",
        detail: "Сервер отклонил токен: он отозван или просрочен.",
      };
    },
    configureWorld: (world) => {
      world.credentials = initialCredentials(true);
    },
  },
  {
    id: "offline",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "ahead", 2, 0);
      project.health = "offline";
      project.lastError = {
        code: "offline",
        detail: "Не удалось связаться с github.com.",
        at: isoAgo(MINUTE),
      };
      project.failWith = {
        code: "offline",
        detail: "Не удалось связаться с github.com.",
      };
    },
  },
  {
    id: "error",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "diverged", 2, 1);
      project.health = "error";
      project.lastError = {
        code: "git_error",
        detail:
          "error: RPC failed; HTTP 500 curl 22 The requested URL returned error: 500",
        at: isoAgo(5 * MINUTE),
      };
      project.failWith = {
        code: "git_error",
        detail:
          "error: RPC failed; HTTP 500 curl 22 The requested URL returned error: 500",
      };
    },
  },
  {
    id: "schema_newer",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "behind", 0, 2);
      project.blocked = {
        reason: "remote_schema_newer",
        required_studio: "0.4.0",
      };
    },
  },
  {
    id: "off_branch",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "ahead", 1, 0);
      project.blocked = { reason: "off_branch" };
    },
  },
  {
    id: "read_only",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "behind", 0, 1);
      project.blocked = { reason: "read_only" };
    },
  },
  {
    id: "no_profile",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "ahead", 2, 0);
      project.botAuthored = 14;
    },
    configureWorld: (world) => {
      world.profile = null;
    },
  },
  {
    id: "shared_folder",
    group: "problem",
    setup: (project) => {
      connected(project);
      setRelation(project, "in_sync");
      project.sharedFolder = {
        provider: "yandex_disk",
        root: "/Users/ivan/Yandex.Disk",
      };
    },
    configureWorld: (world) => {
      world.dataDirShared = {
        provider: "yandex_disk",
        root: "/Users/ivan/Yandex.Disk",
      };
    },
  },
];

export const DEFAULT_SCENARIO_ID: DemoScenarioId = "not_connected";

export const findScenario = (id: string): DemoScenario => {
  const found =
    SCENARIOS.find((scenario) => scenario.id === id) ??
    SCENARIOS.find((scenario) => scenario.id === DEFAULT_SCENARIO_ID);
  if (!found) throw new Error("demo scenarios are not defined");
  return found;
};

export const createWorld = (scenarioId: string): DemoWorld => {
  const scenario = findScenario(scenarioId);
  const world: DemoWorld = {
    scenarioId: scenario.id,
    projects: new Map(),
    operations: new Map(),
    credentials: initialCredentials(false),
    hosts: initialHosts(),
    profile: { name: ME.name, email: ME.email },
    dataDirShared: null,
    newProject: () => emptyProjectGit(),
  };
  scenario.configureWorld?.(world);
  return world;
};

// Проект появляется в мире при первом обращении и сразу получает вид сценария.
export const projectOf = (
  world: DemoWorld,
  projectId: string,
): DemoProjectGit => {
  const existing = world.projects.get(projectId);
  if (existing) return existing;
  const project = emptyProjectGit();
  world.projects.set(projectId, project);
  findScenario(world.scenarioId).setup(project, world, projectId);
  if (!world.profile) {
    project.blocked ??= { reason: "profile_required" };
  }
  return project;
};

export { CLONE_STEPS };
