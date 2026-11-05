import { z } from "zod";
import type { CompileWait } from "@entities/session";

/**
 * Тишина запущенной сборки, после которой показываем тревогу: 5 минут, как простой раннера (300 с).
 * Очередь сюда не входит: пока раннер не взял задачу, молчание нормально.
 */
export const STALL_AFTER_MS = 300_000;

/** Без событий `phase` (локальный режим, старый сервер) сборка стартует сразу, и порог прежний. */
export const LEGACY_STALL_AFTER_MS = 90_000;

/** Тело события `phase` потока сборки: очередь или запуск раннером, времена и загрузка раннеров. */
export const CompilePhaseSchema = z.object({
  phase: z.enum(["queued", "running"]),
  queued_at: z.string(),
  started_at: z.string().nullable(),
  runners_busy: z.number().int().min(0).nullable().optional(),
  runners_capacity: z.number().int().min(0).nullable().optional(),
});
export type CompilePhaseEvent = z.infer<typeof CompilePhaseSchema>;

export const parsePhase = (data: unknown): CompilePhaseEvent | null => {
  const parsed = CompilePhaseSchema.safeParse(data);
  return parsed.success ? parsed.data : null;
};

/** Состояние сборки документа для подписи и плашки. */
export type BuildState =
  | { kind: "idle" }
  /** Кнопка нажата, ответа сервера о фазе ещё нет. */
  | { kind: "starting" }
  | {
      kind: "queued";
      /** Место в очереди, с 1. */
      position: number | null;
      /** Раннеры заняты: сколько задач ведут и сколько могут вести. */
      busy: number | null;
      capacity: number | null;
      /** Ждём личный раннер владельца проекта. */
      personal: boolean;
      /** Нет подходящего онлайн-раннера (теги, офлайн). */
      noRunner: boolean;
      /** Раннер пропал, идёт повтор. */
      retry: { attempt: number; max: number } | null;
    }
  | { kind: "running"; elapsedMs: number }
  | { kind: "silent"; silentMs: number; elapsedMs: number };

type SlotLike = {
  status: "running" | "success" | "failure" | "cancelled";
  phase: "queued" | "running" | null;
  wait: CompileWait | null;
  runStartedAt: number | null;
  lastEventAt: number;
  isStalled: boolean;
  load: { busy: number; capacity: number } | null;
};

/** Порог молчания для слота: очередь не молчит «зря», запущенная сборка и старый режим считаются по порогам. */
export const stallThresholdOf = (slot: SlotLike): number | null => {
  if (slot.status !== "running" || slot.wait !== null) return null;
  if (slot.phase === "queued") return null;
  return slot.phase === "running" ? STALL_AFTER_MS : LEGACY_STALL_AFTER_MS;
};

export const isSlotStalled = (slot: SlotLike, now: number): boolean => {
  const threshold = stallThresholdOf(slot);
  return threshold !== null && now - slot.lastEventAt > threshold;
};

export const buildStateOf = (
  slot: SlotLike | undefined,
  now: number,
): BuildState => {
  if (slot?.status !== "running") return { kind: "idle" };
  const wait = slot.wait;
  if (slot.phase === "queued" || wait !== null) {
    return {
      kind: "queued",
      position: wait?.queue_position ?? null,
      busy: slot.load?.busy ?? null,
      capacity: slot.load?.capacity ?? null,
      personal: wait?.reason === "personal_runner",
      noRunner: wait?.reason === "no_runner",
      retry:
        wait?.reason === "runner_lost" &&
        wait.attempt !== null &&
        wait.max_attempts !== null
          ? { attempt: wait.attempt, max: wait.max_attempts }
          : null,
    };
  }
  const elapsedMs = Math.max(0, now - (slot.runStartedAt ?? slot.lastEventAt));
  // Молчание решает сторож хранилища (`isStalled`): он видит часы точнее, чем отрисовка раз в несколько секунд.
  if (slot.isStalled) {
    const threshold = stallThresholdOf(slot) ?? STALL_AFTER_MS;
    return {
      kind: "silent",
      silentMs: Math.max(threshold, now - slot.lastEventAt),
      elapsedMs,
    };
  }
  // Ответа о фазе ещё нет: в локальном режиме его не будет, там сборка идёт сразу.
  if (slot.phase === null) return { kind: "starting" };
  return { kind: "running", elapsedMs };
};

/** «3:05»: время с запуска раннером. */
export const formatElapsed = (ms: number): string => {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes)}:${String(seconds).padStart(2, "0")}`;
};

/** Полных минут молчания, не меньше одной. */
export const silentMinutes = (ms: number): number =>
  Math.max(1, Math.floor(ms / 60_000));
