import { describe, expect, it } from "vitest";
import type { UpdateRun } from "./api/schemas";
import { CODE_REASON, isUnknownOutcome, reasonOf } from "./lib/failureReason";
import { buildProgress, formatDuration, stepIds } from "./lib/progress";
import { buildSupportText } from "./lib/support";

const T0 = Date.parse("2026-11-17T03:00:00Z");
const at = (s: number) => new Date(T0 + s * 1000).toISOString();

type Ev = [number, string, string, string?];
const run = (events: Ev[], patch: Partial<UpdateRun> = {}): UpdateRun => ({
  id: "r1",
  kind: "update",
  trigger: "manual",
  status: "running",
  phase: null,
  from_version: "0.3.1",
  to_version: "0.3.2",
  from_revision: "a",
  to_revision: "b",
  created_at: at(0),
  started_at: at(0),
  finished_at: null,
  duration_s: null,
  backup_run_id: null,
  restore_db: false,
  db_restored: false,
  error_code: null,
  error: null,
  requested_by_name: "Анна",
  events: events.map(([seq, phase, message, level], i) => ({
    seq: seq || i + 1,
    at: at(seq * 10),
    phase,
    level: (level ?? "info") as "info" | "warn" | "error",
    message,
  })),
  ...patch,
});

const states = (r: UpdateRun, executor: "compose" | "kubernetes", now = 0) =>
  Object.fromEntries(
    buildProgress(r, executor, T0 + now * 1000).steps.map((s) => [
      s.id,
      s.state,
    ]),
  );

describe("ход обновления из журнала", () => {
  it("идущий запуск: пройденное готово, текущее идёт, остальное ждёт, длительность считается", () => {
    const r = run([
      [1, "preflight", "picked up"],
      [2, "snapshot", "db snapshot"],
      [20, "pull", "pulling"],
    ]);
    const p = buildProgress(r, "compose", T0 + 400_000);
    expect(
      Object.fromEntries(p.steps.map((s) => [s.id, s.state])),
    ).toMatchObject({
      check: "done",
      snapshot: "done",
      pull: "active",
      verify: "pending",
      done: "pending",
    });
    expect(p.position).toEqual({ index: 3, total: 9, id: "pull" });
    // идущий этап: от своего первого события до «сейчас»
    expect(p.steps.find((s) => s.id === "pull")?.durationS).toBe(200);
  });

  it("Kubernetes: снимка базы нет, образ тянет проверочный Job в фазе preflight", () => {
    expect(stepIds("kubernetes", run([]))).not.toContain("snapshot");
    const r = run([
      [1, "preflight", "picked up by the updater"],
      [
        2,
        "preflight",
        "checking the new image and reading the database revision (x)",
      ],
    ]);
    expect(states(r, "kubernetes")).toMatchObject({
      check: "done",
      pull: "active",
    });
  });

  it("бэкап показан только когда он был", () => {
    expect(stepIds("compose", run([]))).not.toContain("backup");
    const waiting = run([[1, "backup", "full backup"]], {
      status: "waiting_backup",
    });
    expect(stepIds("compose", waiting)[0]).toBe("backup");
    expect(states(waiting, "compose").backup).toBe("active");
  });

  it("успех: все этапы готовы", () => {
    const r = run(
      [
        [1, "preflight", "a"],
        [2, "health", "waiting"],
        [3, "finish", "done"],
      ],
      { status: "succeeded", finished_at: at(60), duration_s: 60 },
    );
    expect(new Set(Object.values(states(r, "compose")))).toEqual(
      new Set(["done"]),
    );
  });

  it("ошибка на миграции: до неё готово, она упала, после пропущено, откат виден", () => {
    const r = run(
      [
        [1, "preflight", "a"],
        [2, "pull", "b"],
        [3, "stop", "c"],
        [4, "migrate", "migrations failed", "error"],
        [5, "rollback", "rolling back", "error"],
        [6, "finish", "rolled back", "error"],
      ],
      {
        status: "rolled_back",
        error_code: "migration_failed",
        finished_at: at(80),
      },
    );
    const p = buildProgress(r, "compose", T0 + 100_000);
    const by = Object.fromEntries(p.steps.map((s) => [s.id, s.state]));
    expect(by).toMatchObject({
      pull: "done",
      stop: "done",
      migrate: "failed",
      restart: "skipped",
      health: "skipped",
    });
    expect(p.recovery.map((x) => [x.id, x.state])).toEqual([
      ["rollback", "done"],
    ]);
  });

  it("откат не удался: восстановление помечено ошибкой", () => {
    const r = run(
      [
        [1, "stop", "c"],
        [2, "health", "not healthy", "error"],
        [3, "rollback", "back", "warn"],
        [4, "restore", "restoring", "error"],
      ],
      { status: "failed", error_code: "restore_failed" },
    );
    const p = buildProgress(r, "compose", T0);
    expect(p.recovery.at(-1)).toMatchObject({ id: "restore", state: "failed" });
  });

  it("отмена до начала работ: ничего не помечено ошибкой", () => {
    const r = run([[1, "request", "queued"]], {
      status: "cancelled",
      error_code: "cancelled",
    });
    const s = states(r, "compose");
    expect(Object.values(s)).not.toContain("failed");
  });

  it("очередь: идущего этапа нет", () => {
    const r = run([], { status: "queued" });
    const p = buildProgress(r, "compose", T0);
    expect(p.position).toBeNull();
    expect(new Set(Object.values(states(r, "compose")))).toEqual(
      new Set(["pending"]),
    );
  });
});

describe("время", () => {
  it("секунды в читаемую длительность", () => {
    const u = { h: "ч", min: "мин", s: "с" };
    expect(formatDuration(200, u)).toBe("3 мин 20 с");
    expect(formatDuration(0, u)).toBe("0 с");
    expect(formatDuration(3725, u)).toBe("1 ч 2 мин 5 с");
  });
});

describe("причины неудачи", () => {
  const cases: [string | null, string | null, string][] = [
    [
      "precheck_failed",
      "nothing changed: the Job x did not start in 300 s: ErrImagePull",
      "image_pull",
    ],
    [
      "precheck_failed",
      "nothing changed: ... manifest unknown: manifest unknown",
      "image_not_found",
    ],
    [
      "pull_failed",
      "pull failed: Error: manifest for x not found",
      "image_not_found",
    ],
    ["kube_forbidden", "cannot write", "no_permission"],
    [
      "patch_failed",
      "cannot patch the api Deployment: (403) Forbidden: deployments.apps is forbidden",
      "no_permission",
    ],
    ["health_timeout", "x", "rollout_timeout"],
    ["stop_timeout", "x", "rollout_timeout"],
    ["migration_failed", "migrations failed", "migration_failed"],
    [
      "health_failed",
      "the api pod cannot start: CrashLoopBackOff",
      "health_failed",
    ],
    ["digest_missing", "x", "digest"],
    ["updater_lost", "silent", "unknown_outcome"],
    ["updater_restarted", "x", "unknown_outcome"],
    ["needs_manual_action", "x", "needs_hands"],
    ["rollback_failed", "x", "rollback_failed"],
    ["something_new", "x", "unknown"],
    [null, null, "unknown"],
  ];
  it.each(cases)("%s / %s -> %s", (code, message, reason) => {
    expect(reasonOf(code, message)).toBe(reason);
  });

  it("неизвестный исход назван неизвестным", () => {
    expect(isUnknownOutcome(reasonOf("updater_lost", null))).toBe(true);
    expect(isUnknownOutcome(reasonOf("migration_failed", null))).toBe(false);
  });

  it("у каждой группы причин есть заголовок, текст и подсказка на двух языках", async () => {
    const ru = (await import("@shared/lib/i18n/locales/ru/admin/updates.json"))
      .default as { reason: Record<string, Record<string, string>> };
    const en = (await import("@shared/lib/i18n/locales/en/admin/updates.json"))
      .default as { reason: Record<string, Record<string, string>> };
    const groups = new Set([...Object.values(CODE_REASON), "unknown"]);
    for (const g of groups) {
      for (const dict of [ru, en]) {
        expect(Object.keys(dict.reason[g] ?? {}).sort()).toEqual([
          "body",
          "hint",
          "title",
        ]);
      }
    }
  });
});

type Dict = {
  step: Record<string, unknown>;
  state: Record<string, unknown>;
  progress: { recovery: Record<string, string> };
};

describe("словари этапов", () => {
  it("у каждого этапа, состояния и шага отката есть текст в ru и en", async () => {
    const ru = (await import("@shared/lib/i18n/locales/ru/admin/updates.json"))
      .default as unknown as Dict;
    const en = (await import("@shared/lib/i18n/locales/en/admin/updates.json"))
      .default as unknown as Dict;
    const ids = stepIds("compose", {
      status: "waiting_backup",
      backup_run_id: null,
      events: [],
    });
    for (const dict of [ru, en]) {
      for (const id of ids) {
        expect(dict.step[id]).toHaveProperty("title");
        expect(dict.step[id]).toHaveProperty("running");
      }
      for (const st of ["pending", "active", "done", "failed", "skipped"]) {
        expect(typeof dict.state[st]).toBe("string");
      }
      expect(Object.keys(dict.progress.recovery).sort()).toEqual([
        "restore",
        "rollback",
      ]);
    }
  });
});

describe("подробности для поддержки", () => {
  it("содержат код, версии, этап и хвост журнала, без лишнего", () => {
    const r = run(
      [
        [1, "stop", "scaling"],
        [2, "migrate", "migrations failed: [path]", "error"],
      ],
      {
        status: "failed",
        error_code: "migration_failed",
        error: "migrations failed: [path]",
      },
    );
    const text = buildSupportText(
      r,
      "kubernetes",
      "0.3.1",
      buildProgress(r, "kubernetes", T0),
    );
    expect(text).toContain("error code: migration_failed");
    expect(text).toContain("versions: 0.3.1 -> 0.3.2");
    expect(text).toContain("stopped at: migrate");
    expect(text).toContain("ERROR migrate: migrations failed");
    expect(text).not.toContain("Анна");
  });
});
