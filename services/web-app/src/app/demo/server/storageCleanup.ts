import type { DemoRoute } from "@shared/api/demo";
import type { RunnerDiskBrief } from "@entities/runner";
import type { AdminRunner } from "@entities/session";
import {
  createRunnerDiskDemo,
  type DiskDemoActor,
  type DiskDemoProfile,
  type DiskDemoRunner,
  type RunnerDiskDemo,
} from "@entities/runner/testing";
import {
  createLifecycleSweepDemo,
  type LifecycleSweepDemo,
  type SweepDemoProfile,
} from "@features/admin-ops/testing";
import { adminOpsOf, personalOf, type ServerDemoWorld } from "./world";

// Очистка места из админки в демо-мире (docs/design/storage-cleanup.md): диски раннеров и
// «Освободить место». Бэкенда ещё нет (B5–B7), поэтому мир отвечает моками сущностей. Моки
// живут в мире и сбрасываются вместе со сменой сценария.
//
// Какой диск у какого раннера (по сценарию раннеров «Раннеры» и «Личные раннеры»):
//  - runner-1: Docker-раннер с полным замером, есть что освободить;
//  - runner-2: Kubernetes, только кэш раннера;
//  - runner-3: старая версия, диска нет («Обновите раннер»);
//  - runner-4: нечего освобождать;
//  - runner-5: замер старше суток (и раннер не на связи);
//  - остальные общие: замера ещё нет;
//  - личные раннеры на локальной Студии: только кэш раннера; без возможностей: старая
//    версия; остальные личные: Docker-раннер (админу без флажка отката).
// Сводка «Хранилища»: в ops_fresh раннеров нет, в остальных мирах runner-1, runner-4, runner-5.
// «Освободить место»: ops_fresh отвечает «нечего», ops_services_degraded упирается в потолок.

const SHARED_PROFILES: Record<string, DiskDemoProfile> = {
  rn_01hxb1: "docker",
  rn_01hxb2: "kubernetes",
  rn_01hxb3: "outdated",
  rn_01hxb4: "clean",
  rn_01hxb5: "stale",
};

const ONLINE_S = 300;
const isOnline = (lastSeenAt: string | null, offline = false): boolean =>
  !offline &&
  lastSeenAt !== null &&
  (Date.now() - Date.parse(lastSeenAt)) / 1000 <= ONLINE_S;

const actorOf = (world: ServerDemoWorld): DiskDemoActor | null => {
  const user = world.bootstrap.user;
  return user
    ? { id: user.id, name: user.name, admin: user.is_instance_admin }
    : null;
};

const sharedRunner = (r: AdminRunner): DiskDemoRunner => ({
  id: r.id,
  name: r.name,
  online: isOnline(r.last_seen_at),
  last_seen_at: r.last_seen_at,
  revoked: r.revoked,
  owner: null,
});

const personalRunners = (world: ServerDemoWorld) =>
  world.scenario.personalSeed === undefined ? [] : personalOf(world).runners;

const findRunner = (
  world: ServerDemoWorld,
  id: string,
): DiskDemoRunner | null => {
  const shared = adminOpsOf(world).runners.find((r) => r.id === id);
  if (shared) return sharedRunner(shared);
  const personal = personalRunners(world).find((r) => r.id === id);
  if (!personal) return null;
  return {
    id: personal.id,
    name: personal.name,
    online: isOnline(personal.last_seen_at, personal.offline),
    last_seen_at: personal.last_seen_at,
    revoked: personal.revoked_at !== null,
    owner: { id: personal.owner.id, name: personal.owner.name },
  };
};

const profileOf = (
  world: ServerDemoWorld,
  runner: DiskDemoRunner,
): DiskDemoProfile => {
  if (runner.owner === null) return SHARED_PROFILES[runner.id] ?? "no_report";
  const personal = personalRunners(world).find((r) => r.id === runner.id);
  if (!personal || personal.features.length === 0) return "outdated";
  return personal.host_kind === "desktop" ? "desktop" : "docker";
};

/** Диск раннеров мира; строится при первом обращении. */
export const runnerDiskOf = (world: ServerDemoWorld): RunnerDiskDemo => {
  world.runnerDisk ??= createRunnerDiskDemo({
    getActor: () => actorOf(world),
    findRunner: (id) => findRunner(world, id),
    sharedRunners: () => adminOpsOf(world).runners.map(sharedRunner),
    profileOf: (runner) => profileOf(world, runner),
  });
  return world.runnerDisk;
};

const sweepProfile = (world: ServerDemoWorld): SweepDemoProfile =>
  world.scenario.opsSeed === "fresh"
    ? "nothing"
    : world.scenario.opsSeed === "services_degraded"
      ? "capped"
      : "default";

/** «Освободить место» мира; строится при первом обращении. */
export const lifecycleSweepOf = (
  world: ServerDemoWorld,
): LifecycleSweepDemo => {
  world.lifecycleSweep ??= createLifecycleSweepDemo({
    getActor: () => actorOf(world),
    profile: () => sweepProfile(world),
  });
  return world.lifecycleSweep;
};

/** Поле `disk` строки списка раннеров: у отозванного null, как у сервера. */
export const diskBriefOf = (
  world: ServerDemoWorld,
  runnerId: string,
): RunnerDiskBrief | null => {
  const runner = findRunner(world, runnerId);
  return runner && !runner.revoked ? runnerDiskOf(world).brief(runner) : null;
};

/**
 * Маршруты собираются один раз, а моки живут в мире: обработчик находит тот же адрес у
 * моков текущего мира. Образец адресов берётся у заготовки, которая ни к чему не обращается.
 */
const delegate = (
  template: DemoRoute[],
  current: () => DemoRoute[],
): DemoRoute[] =>
  template.map((route) => ({
    ...route,
    handler: (req) => {
      const live = current().find(
        (r) => r.method === route.method && r.pattern === route.pattern,
      );
      if (!live) throw new Error(`storage cleanup demo: ${route.pattern}`);
      return live.handler(req);
    },
  }));

const TEMPLATE_DISK = createRunnerDiskDemo({
  getActor: () => null,
  findRunner: () => null,
  sharedRunners: () => [],
  profileOf: () => "no_report",
});
const TEMPLATE_SWEEP = createLifecycleSweepDemo({
  getActor: () => null,
  profile: () => "default",
});

/** Маршруты клиента /api/admin: диск раннеров, сводка и «Освободить место». */
export const createStorageCleanupAdminRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  ...delegate(
    TEMPLATE_DISK.adminRoutes,
    () => runnerDiskOf(getWorld()).adminRoutes,
  ),
  ...delegate(TEMPLATE_SWEEP.routes, () => lifecycleSweepOf(getWorld()).routes),
];

/** Маршруты клиента /api/v1: диск своих раннеров в «Моих раннерах». */
export const createStorageCleanupAccountRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] =>
  delegate(
    TEMPLATE_DISK.accountRoutes,
    () => runnerDiskOf(getWorld()).accountRoutes,
  );
