import type { UpdateRun } from "../api/schemas";

/** Этапы обновления в порядке выполнения. Не все бывают у каждого исполнителя (снимка базы в Kubernetes нет). */
export type StepId =
  | "backup"
  | "check"
  | "snapshot"
  | "pull"
  | "verify"
  | "stop"
  | "migrate"
  | "restart"
  | "health"
  | "done";

export type StepState = "pending" | "active" | "done" | "failed" | "skipped";

export type Step = {
  id: StepId;
  state: StepState;
  /** Время первого события этапа (ISO) или null, если этап не начинался. */
  startedAt: string | null;
  /** Сколько длился или длится этап. Идущему этапу нужно `nowMs`. */
  durationS: number | null;
  /** Последнее сообщение исполнителя по этапу (уже очищено сервером). */
  message: string | null;
};

/** Откат и восстановление базы показываются после основных этапов, только если они были. */
export type RecoveryStep = {
  id: "rollback" | "restore";
  state: "active" | "done" | "failed";
  durationS: number | null;
  message: string | null;
};

export type Progress = {
  steps: Step[];
  recovery: RecoveryStep[];
  /** Номер идущего (или упавшего) этапа с единицы и общее число этапов. */
  position: { index: number; total: number; id: StepId } | null;
};

export type Executor = "compose" | "kubernetes" | "none";

const BASE_ORDER: StepId[] = [
  "backup",
  "check",
  "snapshot",
  "pull",
  "verify",
  "stop",
  "migrate",
  "restart",
  "health",
  "done",
];

/** Какие этапы показывать: в Kubernetes нет снимка базы, а запрос и бэкап показываем, только если они были. */
export const stepIds = (
  executor: Executor,
  run: Pick<UpdateRun, "status" | "backup_run_id" | "events">,
): StepId[] => {
  const hadBackup =
    run.status === "waiting_backup" ||
    run.backup_run_id !== null ||
    run.events.some((e) => e.phase === "backup");
  return BASE_ORDER.filter((id) => {
    if (id === "snapshot") return executor !== "kubernetes";
    if (id === "backup") return hadBackup;
    return true;
  });
};

const PHASE_STEP: Record<string, StepId | undefined> = {
  request: "backup",
  backup: "backup",
  preflight: "check",
  snapshot: "snapshot",
  pull: "pull",
  verify: "verify",
  stop: "stop",
  migrate: "migrate",
  restart: "restart",
  health: "health",
};

/**
 * Этап события. В Kubernetes образ тянет проверочный Job в фазе `preflight`, поэтому его события
 * ("checking the new image", "database revision") относятся к этапу «образ на узле».
 */
const stepOfEvent = (
  phase: string,
  message: string,
  executor: Executor,
): StepId | null => {
  if (
    executor === "kubernetes" &&
    phase === "preflight" &&
    /checking the new image|database revision/i.test(message)
  ) {
    return "pull";
  }
  return PHASE_STEP[phase] ?? null;
};

const secondsBetween = (fromIso: string, toMs: number): number =>
  Math.max(0, Math.round((toMs - Date.parse(fromIso)) / 1000));

type Seen = { id: StepId; at: string; message: string; level: string };

const resolveStep = (
  tail: boolean,
  lastStep: StepId | null,
  phase: string,
  message: string,
  executor: Executor,
): StepId | null => (tail ? lastStep : stepOfEvent(phase, message, executor));

const isActive = (run: UpdateRun): boolean =>
  run.status === "waiting_backup" ||
  run.status === "queued" ||
  run.status === "running";

type Recovery = Record<
  "rollback" | "restore",
  { first: string; last: string; message: string } | undefined
>;

/**
 * Разбор журнала запуска на этапы: что готово, что идёт, где упало. Всё считается из событий
 * (`phase`, `at`, `level`), а не из отдельного состояния, поэтому после перезапуска api вид тот же.
 */
export const buildProgress = (
  run: UpdateRun,
  executor: Executor,
  nowMs: number,
): Progress => {
  const ids = stepIds(executor, run);
  const events = [...run.events].sort((a, b) => a.seq - b.seq);
  const seen: Seen[] = [];
  const recovery: Recovery = { rollback: undefined, restore: undefined };
  let lastStep: StepId | null = null;
  let failedStep: StepId | null = null;
  let lastPhase = "";
  for (const e of events) {
    lastPhase = e.phase;
    if (e.phase === "rollback" || e.phase === "restore") {
      const prev = recovery[e.phase];
      recovery[e.phase] = {
        first: prev?.first ?? e.at,
        last: e.at,
        message: e.message,
      };
      if (e.level === "error" && failedStep === null) failedStep = lastStep;
      continue;
    }
    const tail = e.phase === "finish" || e.phase === "cleanup";
    const id = resolveStep(tail, lastStep, e.phase, e.message, executor);
    if (id === null) continue;
    if (!tail) lastStep = id;
    seen.push({ id, at: e.at, message: e.message, level: e.level });
    if (e.level === "error" && failedStep === null) failedStep = id;
  }

  const active = isActive(run);
  const index = (id: StepId | null): number =>
    id === null ? -1 : ids.indexOf(id);
  const maxSeen = seen.reduce((m, s) => Math.max(m, index(s.id)), -1);
  const succeeded = run.status === "succeeded";
  let failIdx = -1;
  if (!active && !succeeded) {
    failIdx = index(failedStep);
    if (failIdx < 0 && run.status !== "cancelled") {
      failIdx = maxSeen >= 0 ? maxSeen : 0;
    }
  }
  let activeIdx = -1;
  if (active) {
    activeIdx = maxSeen;
    if (activeIdx < 0 && run.status === "waiting_backup") {
      activeIdx = Math.max(0, ids.indexOf("backup"));
    }
  }

  const endMs = run.finished_at ? Date.parse(run.finished_at) : nowMs;
  const firstAt = (id: StepId): string | null =>
    seen.find((s) => s.id === id)?.at ?? null;
  const lastMessage = (id: StepId): string | null => {
    const mine = seen.filter((s) => s.id === id);
    return mine.length ? (mine[mine.length - 1]?.message ?? null) : null;
  };

  const steps: Step[] = ids.map((id, i) => {
    let state: StepState;
    if (succeeded) state = "done";
    else if (active)
      state = i < activeIdx ? "done" : i === activeIdx ? "active" : "pending";
    else if (failIdx >= 0)
      state = i < failIdx ? "done" : i === failIdx ? "failed" : "skipped";
    else state = i <= maxSeen ? "done" : "skipped";
    const startedAt = firstAt(id);
    let durationS: number | null = null;
    if (startedAt !== null && id !== "done") {
      const next = ids
        .slice(i + 1)
        .map(firstAt)
        .find((at) => at !== null);
      const stopMs = next
        ? Date.parse(next)
        : state === "failed" && recovery.rollback
          ? Date.parse(recovery.rollback.first)
          : endMs;
      durationS = Math.max(
        0,
        Math.round((stopMs - Date.parse(startedAt)) / 1000),
      );
    }
    return {
      id,
      state,
      startedAt,
      durationS,
      message: lastMessage(id),
    };
  });

  const recoverySteps: RecoveryStep[] = [];
  for (const id of ["rollback", "restore"] as const) {
    const r = recovery[id];
    if (!r) continue;
    let state: RecoveryStep["state"];
    if (active) state = lastPhase === id ? "active" : "done";
    else if (run.status === "rolled_back") state = "done";
    else state = id === "restore" && run.db_restored ? "done" : "failed";
    recoverySteps.push({
      id,
      state,
      durationS: Math.max(
        0,
        Math.round(
          ((state === "active" ? nowMs : Date.parse(r.last)) -
            Date.parse(r.first)) /
            1000,
        ),
      ),
      message: r.message,
    });
  }

  const at = active ? activeIdx : failIdx;
  const position =
    at >= 0 && ids[at] !== undefined
      ? { index: at + 1, total: ids.length, id: ids[at] }
      : null;
  return { steps, recovery: recoverySteps, position };
};

/** Секунды в «3 мин 20 с» по словарю единиц. */
export const formatDuration = (
  seconds: number,
  units: { h: string; min: string; s: string },
): string => {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const parts: string[] = [];
  if (h) parts.push(`${String(h)} ${units.h}`);
  if (m) parts.push(`${String(m)} ${units.min}`);
  if (s || parts.length === 0) parts.push(`${String(s)} ${units.s}`);
  return parts.join(" ");
};

export const elapsedSince = (iso: string | null, nowMs: number): number =>
  iso === null ? 0 : secondsBetween(iso, nowMs);
