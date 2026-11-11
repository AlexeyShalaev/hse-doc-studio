import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  RunnerDiskCleanupRequestSchema,
  RunnerDiskReportSchema,
  RunnerDiskViewSchema,
} from "./runnerDisk.schema";
import { MyRunnerSchema } from "./runner.schema";
import {
  ALL_TARGETS_STEPS,
  DISK_COMMANDS,
  NO_REPORTS_DISK_SUMMARY,
  RUNNER_DISK_STATES,
  makeRunnerDiskReport,
  makeRunnerDiskSummary,
} from "../testing";
import {
  cleanAllTargets,
  diskCommandPhase,
  diskCommandProgress,
  diskTargetBytes,
  isDiskCommandActive,
  isRunnerDiskBusy,
  runnerDiskMode,
  runnerDiskTotals,
} from "../lib/runnerDiskLib";

// Эталоны контракта лежат в contracts/server/fixtures/RunnerDisk* (их разбирают оба теста контракта:
// entities/session/api/contract.test.ts и test_server_contract.py); здесь проверяется, что состояния
// галерей и моки от них не ушли.

const FIXTURES = join(
  import.meta.dirname,
  ...Array<string>(6).fill(".."),
  "contracts",
  "server",
  "fixtures",
);
const fixture = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));

describe("диск раннера: состояния галерей и эталоны contracts/server", () => {
  it.each([
    "docker",
    "running",
    "done_error",
    "offline",
    "no_report",
    "docker_unavailable",
    "outdated",
    "kubernetes",
    "desktop",
    "personal_admin",
  ] as const)("вид %s совпадает с эталоном", (name) => {
    expect(RUNNER_DISK_STATES[name]).toEqual(fixture("RunnerDiskView", name));
  });

  it.each(["queued", "running", "done", "lost", "measure"] as const)(
    "команда %s совпадает с эталоном",
    (name) => {
      expect(DISK_COMMANDS[name]).toEqual(fixture("RunnerDiskCommand", name));
    },
  );

  it("сводка совпадает с эталонами", () => {
    expect(makeRunnerDiskSummary()).toEqual(
      fixture("RunnerDiskSummary", "default"),
    );
    expect(NO_REPORTS_DISK_SUMMARY).toEqual(
      fixture("RunnerDiskSummary", "none"),
    );
  });

  it.each(Object.entries(RUNNER_DISK_STATES))(
    "состояние галереи %s проходит схему",
    (_id, view) => {
      expect(RunnerDiskViewSchema.parse(view)).toEqual(view);
    },
  );
});

describe("схемы диска раннера", () => {
  it("поле нельзя опустить: пустое значение приходит null", () => {
    const { volume: _volume, ...rest } = makeRunnerDiskReport();
    expect(RunnerDiskReportSchema.safeParse(rest).success).toBe(false);
  });

  it("лишнее поле внутри Docker-части отвергается", () => {
    const report = makeRunnerDiskReport();
    const broken = {
      ...report,
      docker: { ...report.docker, data_root: "/var/lib/docker" },
    };
    expect(RunnerDiskReportSchema.safeParse(broken).success).toBe(false);
  });

  it("запрос очистки: от одной до шести целей без повторов", () => {
    const parse = (targets: string[]) =>
      RunnerDiskCleanupRequestSchema.safeParse({
        targets,
        include_rollback: false,
      }).success;
    expect(parse([])).toBe(false);
    expect(parse(["build_cache", "build_cache"])).toBe(false);
    expect(parse(["images"])).toBe(false);
    expect(parse(["build_cache", "runner_cache"])).toBe(true);
  });

  it("поле disk в «Моих раннерах» обязательно: у отозванного null", () => {
    const runner = {
      id: "r1",
      name: "MacBook",
      state: "online",
      host_kind: "desktop",
      tags: [],
      concurrency: 1,
      ai_concurrency: 0,
      version: "0.22.1",
      created_at: "2026-11-01T00:00:00Z",
      last_seen_at: null,
      last_seen_ip: null,
      paused: false,
      paused_by: null,
      revoked: false,
      running_jobs: 0,
      ai_endpoints: [],
      features: [],
    };
    expect(MyRunnerSchema.safeParse(runner).success).toBe(false);
    const disk = {
      supported: true,
      cleanable_bytes: 10,
      measured_at: "2026-11-11T09:00:00Z",
    };
    expect(MyRunnerSchema.safeParse({ ...runner, disk }).success).toBe(true);
    expect(MyRunnerSchema.safeParse({ ...runner, disk: null }).success).toBe(
      true,
    );
  });
});

describe("правила диалога «Диск»", () => {
  it("режим по виду: каждое особое состояние 4.1", () => {
    expect(runnerDiskMode(RUNNER_DISK_STATES.docker)).toBe("docker");
    expect(runnerDiskMode(RUNNER_DISK_STATES.outdated)).toBe("outdated");
    expect(runnerDiskMode(RUNNER_DISK_STATES.no_report)).toBe("no_report");
    expect(runnerDiskMode(RUNNER_DISK_STATES.kubernetes)).toBe("kubernetes");
    expect(runnerDiskMode(RUNNER_DISK_STATES.desktop)).toBe("desktop");
    expect(runnerDiskMode(RUNNER_DISK_STATES.docker_unavailable)).toBe(
      "docker_unavailable",
    );
  });

  it("фаза команды: ждём, идёт, итог, нечего, ошибки, пропал", () => {
    expect(diskCommandPhase(DISK_COMMANDS.queued)).toBe("waiting");
    expect(diskCommandPhase(DISK_COMMANDS.running)).toBe("running");
    expect(diskCommandPhase(DISK_COMMANDS.done)).toBe("done");
    expect(diskCommandPhase(DISK_COMMANDS.nothing)).toBe("nothing");
    expect(diskCommandPhase(DISK_COMMANDS.error)).toBe("error");
    expect(diskCommandPhase(DISK_COMMANDS.lost)).toBe("lost");
    expect(diskCommandPhase(DISK_COMMANDS.expired)).toBe("expired");
  });

  it("ход: шаг n из total, освобождено и ошибки", () => {
    expect(diskCommandProgress(DISK_COMMANDS.running)).toMatchObject({
      n: 3,
      total: ALL_TARGETS_STEPS.length,
      errors: 0,
    });
    expect(diskCommandProgress(DISK_COMMANDS.error).errors).toBe(2);
    expect(diskCommandProgress(DISK_COMMANDS.queued)).toMatchObject({
      n: 1,
      total: 0,
      freed: 0,
    });
  });

  it("быстрый опрос только пока команда не закрыта или идёт замер", () => {
    expect(isDiskCommandActive(DISK_COMMANDS.cancelling)).toBe(true);
    expect(isDiskCommandActive(DISK_COMMANDS.done)).toBe(false);
    expect(isRunnerDiskBusy(RUNNER_DISK_STATES.running)).toBe(true);
    expect(isRunnerDiskBusy(RUNNER_DISK_STATES.measuring)).toBe(true);
    expect(isRunnerDiskBusy(RUNNER_DISK_STATES.done)).toBe(false);
    expect(isRunnerDiskBusy(undefined)).toBe(false);
  });

  it("можно освободить: все цели «Очистить всё» без отката, плюс кэш раннера", () => {
    const report = makeRunnerDiskReport();
    const docker = report.docker;
    if (!docker) throw new Error("docker report expected");
    const byTargets = cleanAllTargets(report).reduce(
      (acc, target) => acc + diskTargetBytes(report, target),
      0,
    );
    expect(runnerDiskTotals(report).cleanable).toBe(byTargets);
    expect(diskTargetBytes(report, "old_versions", true)).toBe(
      docker.old_versions.reclaimable_bytes +
        docker.old_versions.rollback_bytes,
    );
  });

  it("Kubernetes: освободить можно только кэш раннера", () => {
    const report = RUNNER_DISK_STATES.kubernetes.report;
    if (!report) throw new Error("report expected");
    expect(cleanAllTargets(report)).toEqual(["runner_cache"]);
    expect(diskTargetBytes(report, "build_cache")).toBe(0);
    expect(runnerDiskTotals(report).cleanable).toBe(
      report.cache.blobs.bytes + report.cache.workspaces.bytes,
    );
  });
});
