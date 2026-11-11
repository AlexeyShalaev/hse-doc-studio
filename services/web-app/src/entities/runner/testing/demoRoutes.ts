import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRequest, DemoResponse, DemoRoute } from "@shared/api/demo";
import { runnerDiskTotals } from "../lib/runnerDiskLib";
import {
  DISK_TARGETS,
  type DiskStep,
  type DiskTarget,
  type PersonRef,
  type RunnerCacheDisk,
  type RunnerDiskBrief,
  type RunnerDiskCommand,
  type RunnerDiskReport,
  type RunnerDiskSummary,
  type RunnerDiskView,
} from "../model/runnerDisk.schema";
import {
  DISK_MIN_VERSION,
  DOCKER_TARGETS,
  GIB,
  dockerDiskOf,
  emptyRunnerCacheDisk,
  makeCleanDiskInventory,
  makeDesktopDiskReport,
  makeDiskInventory,
  makeKubernetesDiskReport,
  makeRunnerCacheDisk,
  unavailableDockerDisk,
  type DiskInventory,
} from "./fixtures";

// Моки диска раннера поверх демо-транспорта (docs/design/storage-cleanup.md, 5.3 и 9.1): те же
// адреса, коды ошибок и переходы команды, что у сервера, в упрощённом виде. Ход идёт по опросу:
// каждый GET вида продвигает очистку на один шаг, замер готов на втором опросе. Бэкенда (B5, B6)
// ещё нет: на этих моках работают экраны W3–W6 и серверное демо.

/** Раннер, как его видит демо: общий (`owner: null`) или личный. */
export type DiskDemoRunner = {
  id: string;
  name: string;
  /** На связи сейчас: иначе очистка и «Обновить» дают 409 runner_offline. */
  online: boolean;
  last_seen_at: string | null;
  revoked: boolean;
  owner: PersonRef | null;
};

export type DiskDemoActor = { id: string; name: string; admin: boolean };

/**
 * С чего начинается диск раннера: полный Docker-замер, вычищенный, Kubernetes, локальная
 * Студия, Docker не ответил, старая версия, замера ещё нет, замер старше суток.
 */
export type DiskDemoProfile =
  | "docker"
  | "clean"
  | "kubernetes"
  | "desktop"
  | "docker_unavailable"
  | "outdated"
  | "no_report"
  | "stale";

export type RunnerDiskDemoOptions = {
  getActor: () => DiskDemoActor | null;
  findRunner: (id: string) => DiskDemoRunner | null;
  /** Общие раннеры установки: из них сводка «Хранилища». */
  sharedRunners: () => DiskDemoRunner[];
  profileOf: (runner: DiskDemoRunner) => DiskDemoProfile;
  now?: () => number;
};

export type RunnerDiskDemo = {
  /** Маршруты клиента /api/admin. */
  adminRoutes: DemoRoute[];
  /** Маршруты клиента /api/v1 («Мои раннеры»). */
  accountRoutes: DemoRoute[];
  /** Поле `disk` строки списка раннеров. */
  brief: (runner: DiskDemoRunner) => RunnerDiskBrief;
  /** Поставить раннеру профиль заново (тесты и галереи). */
  seed: (runnerId: string, profile: DiskDemoProfile) => void;
  reset: () => void;
};

type Scope = "admin" | "account";

type PlannedStep = { step: DiskStep; bytes: number; apply: () => void };

type DemoCommand = {
  command: RunnerDiskCommand;
  plan: PlannedStep[];
};

type DiskState = {
  supported: boolean;
  kind: "docker" | "kubernetes" | "desktop" | "docker_unavailable";
  inventory: DiskInventory | null;
  cache: RunnerCacheDisk;
  volume: { total_bytes: number; free_bytes: number } | null;
  /** null: раннер ещё не прислал замер. */
  measuredAt: number | null;
  receivedAt: number | null;
  cleanup: DemoCommand | null;
  measure: { command: RunnerDiskCommand; polls: number } | null;
};

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;
const ACTIVE = new Set(["queued", "delivered", "running", "cancelling"]);

const iso = (ms: number): string => new Date(ms).toISOString();

const notFound = () => demoError(404, "not_found", "Not Found");
const invalid = () =>
  demoError(422, "input_invalid", "targets must be 1..6 unique disk targets");

export const createRunnerDiskDemo = (
  options: RunnerDiskDemoOptions,
): RunnerDiskDemo => {
  const now = options.now ?? Date.now;
  const states = new Map<string, DiskState>();
  let commandCounter = 0;

  const initial = (profile: DiskDemoProfile): DiskState => {
    const t = now();
    const base: DiskState = {
      supported: true,
      kind: "docker",
      inventory: makeDiskInventory(),
      cache: makeRunnerCacheDisk(),
      volume: { total_bytes: 200 * GIB, free_bytes: Math.round(23.5 * GIB) },
      measuredAt: t - 40 * 60 * 1000,
      receivedAt: t - 40 * 60 * 1000 + 2000,
      cleanup: null,
      measure: null,
    };
    switch (profile) {
      case "docker":
        return base;
      case "clean":
        return {
          ...base,
          inventory: makeCleanDiskInventory(),
          cache: emptyRunnerCacheDisk(),
          volume: { total_bytes: 200 * GIB, free_bytes: 41 * GIB },
        };
      case "stale":
        return {
          ...base,
          measuredAt: t - 30 * HOUR,
          receivedAt: t - 30 * HOUR + 2000,
        };
      case "kubernetes": {
        const r = makeKubernetesDiskReport();
        return {
          ...base,
          kind: "kubernetes",
          inventory: null,
          cache: r.cache,
          volume: r.volume,
        };
      }
      case "desktop": {
        const r = makeDesktopDiskReport();
        return {
          ...base,
          kind: "desktop",
          inventory: null,
          cache: r.cache,
          volume: r.volume,
        };
      }
      case "docker_unavailable":
        return { ...base, kind: "docker_unavailable", inventory: null };
      case "outdated":
        return {
          ...base,
          supported: false,
          measuredAt: null,
          receivedAt: null,
        };
      case "no_report":
        return { ...base, measuredAt: null, receivedAt: null };
    }
  };

  const stateOf = (runner: DiskDemoRunner): DiskState => {
    let state = states.get(runner.id);
    if (!state) {
      state = initial(options.profileOf(runner));
      states.set(runner.id, state);
    }
    return state;
  };

  const targetsOf = (state: DiskState): DiskTarget[] =>
    state.kind === "docker" ? [...DOCKER_TARGETS] : ["runner_cache"];

  const reportOf = (state: DiskState): RunnerDiskReport | null => {
    if (!state.supported || state.measuredAt === null) return null;
    return {
      measured_at: iso(state.measuredAt),
      targets: targetsOf(state),
      docker:
        state.kind === "docker" && state.inventory
          ? dockerDiskOf(state.inventory)
          : state.kind === "docker_unavailable"
            ? unavailableDockerDisk()
            : null,
      docker_reason:
        state.kind === "kubernetes"
          ? "kubernetes"
          : state.kind === "desktop"
            ? "managed_locally"
            : null,
      cache: structuredClone(state.cache),
      volume: state.volume ? { ...state.volume } : null,
    };
  };

  const remeasure = (state: DiskState): void => {
    state.measuredAt = now();
    state.receivedAt = now();
  };

  // План очистки: как раннер строит его по свежему замеру (5.2), шаг за шагом.
  const planOf = (
    state: DiskState,
    targets: DiskTarget[],
    includeRollback: boolean,
  ): PlannedStep[] => {
    const plan: PlannedStep[] = [];
    const add = (
      kind: DiskStep["kind"],
      ref: string | null,
      bytes: number,
      apply: () => void,
    ) =>
      plan.push({
        step: { kind, ref, status: "pending", freed_bytes: 0, error: null },
        bytes,
        apply,
      });
    const inv = state.inventory;
    const has = (target: DiskTarget) => targets.includes(target);
    if (inv && has("old_versions")) {
      const containers = inv.old.filter((o) => o.kind === "container");
      const images = inv.old.filter((o) => o.kind !== "container");
      for (const item of [...containers, ...images]) {
        add(
          item.kind === "container" ? "container" : "image",
          item.ref,
          item.size_bytes,
          () => {
            inv.old = inv.old.filter((o) => o !== item);
          },
        );
      }
      const rollback = inv.rollback;
      if (includeRollback && rollback) {
        add("image", rollback.ref, rollback.size_bytes, () => {
          inv.rollback = null;
        });
      }
    }
    if (inv && has("stopped_containers")) {
      const { count, bytes } = inv.stopped_containers;
      for (let i = 1; i <= count; i += 1) {
        const share = Math.round(bytes / count);
        add("container", `hse-studio-job-${String(i)}`, share, () => {
          inv.stopped_containers = {
            count: Math.max(0, inv.stopped_containers.count - 1),
            bytes: Math.max(0, inv.stopped_containers.bytes - share),
          };
        });
      }
    }
    if (inv && has("unused_images")) {
      for (const image of inv.unused) {
        add("image", image.ref, image.size_bytes, () => {
          inv.unused = inv.unused.filter((u) => u !== image);
        });
      }
    }
    if (inv && has("dangling_images")) {
      add("dangling_images", null, inv.dangling.bytes, () => {
        inv.dangling = { bytes: 0, count: 0 };
      });
    }
    if (inv && has("build_cache")) {
      const { bytes, reclaimable_bytes } = inv.build_cache;
      add("build_cache", null, reclaimable_bytes, () => {
        inv.build_cache = {
          bytes: bytes - reclaimable_bytes,
          reclaimable_bytes: 0,
          count: 0,
        };
      });
    }
    if (has("runner_cache")) {
      const cache = state.cache;
      add("runner_blobs", null, cache.blobs.bytes, () => {
        cache.blobs = { ...cache.blobs, bytes: 0, count: 0 };
      });
      // Рабочие копии под замком задачи пропускаются (S9).
      const ws = cache.workspaces;
      const kept =
        ws.count > 0 ? Math.round((ws.bytes * ws.busy) / ws.count) : 0;
      add("runner_workspaces", null, ws.bytes - kept, () => {
        cache.workspaces = { ...ws, bytes: kept, count: ws.busy };
      });
    }
    return plan;
  };

  const syncProgress = (demo: DemoCommand): void => {
    const steps = demo.plan.map((p) => ({ ...p.step }));
    demo.command = {
      ...demo.command,
      progress: {
        steps,
        freed_bytes: steps.reduce((acc, s) => acc + s.freed_bytes, 0),
        error: null,
      },
    };
  };

  const finish = (
    state: DiskState,
    demo: DemoCommand,
    final: "done" | "cancelled",
  ): void => {
    syncProgress(demo);
    const freed = demo.command.progress?.freed_bytes ?? 0;
    if (state.volume) {
      state.volume = {
        ...state.volume,
        free_bytes: Math.min(
          state.volume.total_bytes,
          state.volume.free_bytes + freed,
        ),
      };
    }
    demo.command = { ...demo.command, state: final, finished_at: iso(now()) };
    // После итога раннер сам присылает новый замер.
    remeasure(state);
  };

  /** Один опрос: команда продвигается на шаг, замер созревает на втором опросе. */
  const advance = (state: DiskState): void => {
    if (state.measure) {
      state.measure.polls += 1;
      if (state.measure.polls >= 2) {
        state.measure = null;
        remeasure(state);
      }
    }
    const demo = state.cleanup;
    if (!demo || !ACTIVE.has(demo.command.state)) return;
    const { plan } = demo;
    if (demo.command.state === "queued" || demo.command.state === "delivered") {
      const first = plan[0];
      if (first) first.step.status = "running";
      demo.command = { ...demo.command, state: "running" };
      syncProgress(demo);
      if (!first) finish(state, demo, "done");
      return;
    }
    const current = plan.find((p) => p.step.status === "running");
    if (current) {
      current.step.status = "done";
      current.step.freed_bytes = current.bytes;
      current.apply();
    }
    if (demo.command.state === "cancelling") {
      for (const p of plan) {
        if (p.step.status === "pending") p.step.status = "skipped";
      }
      finish(state, demo, "cancelled");
      return;
    }
    const next = plan.find((p) => p.step.status === "pending");
    if (next) {
      next.step.status = "running";
      syncProgress(demo);
      return;
    }
    finish(state, demo, "done");
  };

  const actorFor = (
    scope: Scope,
    runnerId: string | undefined,
  ):
    | { actor: DiskDemoActor; runner: DiskDemoRunner }
    | { error: DemoResponse } => {
    const actor = options.getActor();
    if (!actor) {
      return {
        error: demoError(401, "auth_required", "Authentication required"),
      };
    }
    if (scope === "admin" && !actor.admin) return { error: notFound() };
    const runner = runnerId ? options.findRunner(runnerId) : null;
    if (!runner || runner.revoked) return { error: notFound() };
    if (scope === "account" && runner.owner?.id !== actor.id) {
      return { error: notFound() };
    }
    return { actor, runner };
  };

  const recentCommand = (state: DiskState): RunnerDiskCommand | null => {
    const command = state.cleanup?.command ?? null;
    if (!command) return null;
    if (ACTIVE.has(command.state)) return command;
    const finished = command.finished_at ? Date.parse(command.finished_at) : 0;
    return now() - finished < DAY ? command : null;
  };

  const rollbackAllowed = (scope: Scope, runner: DiskDemoRunner): boolean =>
    !(scope === "admin" && runner.owner !== null);

  const viewOf = (
    scope: Scope,
    runner: DiskDemoRunner,
    state: DiskState,
  ): RunnerDiskView => {
    const report = reportOf(state);
    const busy = state.cleanup
      ? ACTIVE.has(state.cleanup.command.state)
      : false;
    return {
      runner_id: runner.id,
      supported: state.supported,
      reason: state.supported ? null : "outdated",
      min_version: DISK_MIN_VERSION,
      online: runner.online,
      last_seen_at: runner.last_seen_at,
      report,
      received_at:
        report && state.receivedAt !== null ? iso(state.receivedAt) : null,
      stale: state.measuredAt !== null && now() - state.measuredAt > DAY,
      command: recentCommand(state),
      measuring: state.measure !== null,
      can_clean: state.supported && runner.online && report !== null && !busy,
      can_include_rollback:
        rollbackAllowed(scope, runner) &&
        (report?.targets.includes("old_versions") ?? false),
      personal_owner:
        scope === "admin" && runner.owner
          ? { id: runner.owner.id, name: runner.owner.name }
          : null,
    };
  };

  const nextCommandId = (): string => {
    commandCounter += 1;
    return `rdc_demo_${String(commandCounter).padStart(4, "0")}`;
  };

  /** Общие проверки «можно ли ставить команду»: поддержка и связь. */
  const commandRefusal = (
    runner: DiskDemoRunner,
    state: DiskState,
  ): DemoResponse | null => {
    if (!state.supported) {
      return demoError(
        409,
        "runner_disk_unsupported",
        "The runner does not report its disk",
      );
    }
    if (!runner.online) {
      return demoError(409, "runner_offline", "The runner is offline");
    }
    return null;
  };

  const routesFor = (scope: Scope, base: string): DemoRoute[] => {
    const resolve = (req: DemoRequest) => actorFor(scope, req.params.id);
    return [
      {
        method: "GET",
        pattern: `${base}/:id/disk`,
        handler: (req) => {
          const found = resolve(req);
          if ("error" in found) return found.error;
          const state = stateOf(found.runner);
          advance(state);
          return demoJson(viewOf(scope, found.runner, state));
        },
      },
      {
        method: "POST",
        pattern: `${base}/:id/disk/refresh`,
        handler: (req) => {
          const found = resolve(req);
          if ("error" in found) return found.error;
          const { actor, runner } = found;
          const state = stateOf(runner);
          const refusal = commandRefusal(runner, state);
          if (refusal) return refusal;
          if (state.cleanup && ACTIVE.has(state.cleanup.command.state)) {
            return demoError(
              409,
              "runner_disk_busy",
              "A cleanup is already running on this runner",
            );
          }
          state.measure ??= {
            polls: 0,
            command: {
              id: nextCommandId(),
              kind: "disk.measure",
              state: "queued",
              targets: [],
              include_rollback: false,
              created_at: iso(now()),
              finished_at: null,
              created_by: { id: actor.id, name: actor.name },
              progress: null,
            },
          };
          return demoJson(state.measure.command, 202);
        },
      },
      {
        method: "POST",
        pattern: `${base}/:id/disk/cleanup`,
        handler: (req) => {
          const found = resolve(req);
          if ("error" in found) return found.error;
          const { actor, runner } = found;
          const body = (req.body ?? {}) as Record<string, unknown>;
          const targets = body.targets;
          const includeRollback = body.include_rollback;
          if (
            !Array.isArray(targets) ||
            targets.length === 0 ||
            new Set(targets).size !== targets.length ||
            !targets.every((t) =>
              (DISK_TARGETS as readonly unknown[]).includes(t),
            ) ||
            typeof includeRollback !== "boolean"
          ) {
            return invalid();
          }
          const state = stateOf(runner);
          const refusal = commandRefusal(runner, state);
          if (refusal) return refusal;
          if (state.cleanup && ACTIVE.has(state.cleanup.command.state)) {
            return demoError(
              409,
              "runner_disk_busy",
              "A cleanup is already running on this runner",
            );
          }
          if (includeRollback && !rollbackAllowed(scope, runner)) {
            return demoError(
              403,
              "forbidden",
              "Only the owner can remove the rollback version of a personal runner",
            );
          }
          const report = reportOf(state);
          const available = report?.targets ?? [];
          if (!(targets as DiskTarget[]).every((t) => available.includes(t))) {
            return demoError(
              409,
              "disk_target_unavailable",
              "The runner cannot clean this target now",
            );
          }
          const command: RunnerDiskCommand = {
            id: nextCommandId(),
            kind: "disk.cleanup",
            state: "queued",
            targets: [...(targets as DiskTarget[])],
            include_rollback: includeRollback,
            created_at: iso(now()),
            finished_at: null,
            created_by: { id: actor.id, name: actor.name },
            progress: null,
          };
          state.cleanup = {
            command,
            plan: planOf(state, command.targets, includeRollback),
          };
          return demoJson(command, 202);
        },
      },
      {
        method: "POST",
        pattern: `${base}/:id/disk/commands/:cid/cancel`,
        handler: (req) => {
          const found = resolve(req);
          if ("error" in found) return found.error;
          const state = stateOf(found.runner);
          const demo = state.cleanup;
          if (!demo || demo.command.id !== req.params.cid) return notFound();
          const current = demo.command.state;
          if (!ACTIVE.has(current)) {
            return demoError(
              409,
              "command_finished",
              "The command is already finished",
            );
          }
          if (current === "queued") {
            for (const p of demo.plan) p.step.status = "skipped";
            syncProgress(demo);
            demo.command = {
              ...demo.command,
              state: "cancelled",
              finished_at: iso(now()),
            };
          } else if (current !== "cancelling") {
            demo.command = { ...demo.command, state: "cancelling" };
          }
          return demoJson(demo.command);
        },
      },
    ];
  };

  const summary = (): RunnerDiskSummary => {
    const rows = options
      .sharedRunners()
      .filter((r) => !r.revoked)
      .map((runner) => {
        const state = stateOf(runner);
        return { runner, state, report: reportOf(state) };
      });
    const reporting = rows.filter((r) => r.report !== null);
    const cleanable = reporting.map((r) => ({
      runner_id: r.runner.id,
      name: r.runner.name,
      cleanable_bytes: r.report ? runnerDiskTotals(r.report).cleanable : 0,
      measured_at: r.report?.measured_at ?? "",
    }));
    return {
      reporting: reporting.length,
      outdated: rows.filter((r) => !r.state.supported).length,
      min_version: DISK_MIN_VERSION,
      cleanable_bytes: cleanable.reduce((acc, r) => acc + r.cleanable_bytes, 0),
      top: cleanable
        .filter((r) => r.cleanable_bytes > 0)
        .sort((a, b) => b.cleanable_bytes - a.cleanable_bytes)
        .slice(0, 3),
    };
  };

  const adminSummaryRoute: DemoRoute = {
    method: "GET",
    pattern: "/runners/disk-summary",
    handler: () => {
      const actor = options.getActor();
      if (!actor) {
        return demoError(401, "auth_required", "Authentication required");
      }
      if (!actor.admin) return notFound();
      return demoJson(summary());
    },
  };

  return {
    // Сводка раньше адресов с :id, чтобы «disk-summary» не принять за раннер.
    adminRoutes: [adminSummaryRoute, ...routesFor("admin", "/runners")],
    accountRoutes: routesFor("account", "/account/runners"),
    brief: (runner) => {
      const state = stateOf(runner);
      const report = reportOf(state);
      return {
        supported: state.supported,
        cleanable_bytes: report ? runnerDiskTotals(report).cleanable : null,
        measured_at: report?.measured_at ?? null,
      };
    },
    seed: (runnerId, profile) => {
      states.set(runnerId, initial(profile));
    },
    reset: () => {
      states.clear();
      commandCounter = 0;
    },
  };
};
