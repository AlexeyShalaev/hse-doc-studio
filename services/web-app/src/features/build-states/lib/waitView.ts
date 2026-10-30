import type { CompileWait } from "@entities/session";

/** Оттенок плашки: ждём спокойно, нужна помощь администратора, итог без результата. */
export type WaitTone = "info" | "warn" | "err" | "neutral";

export type WaitView = {
  /** Ключ заголовка в documents:compile.wait */
  titleKey: string;
  /** Ключ пояснения в documents:compile.wait */
  bodyKey: string;
  tone: WaitTone;
  /** Сборка ещё может начаться сама (не итог). */
  live: boolean;
};

const VIEWS: Record<CompileWait["reason"], WaitView> = {
  queued: {
    titleKey: "queued",
    bodyKey: "queuedBody",
    tone: "info",
    live: true,
  },
  quota_wait: {
    titleKey: "quota",
    bodyKey: "quotaBody",
    tone: "info",
    live: true,
  },
  no_runner: {
    titleKey: "noRunner",
    bodyKey: "noRunnerBody",
    tone: "err",
    live: true,
  },
  runner_lost: {
    titleKey: "runnerLost",
    bodyKey: "runnerLostBody",
    tone: "warn",
    live: true,
  },
  personal_runner: {
    titleKey: "personalRunner",
    bodyKey: "personalRunnerBody",
    tone: "info",
    live: true,
  },
  superseded: {
    titleKey: "superseded",
    bodyKey: "supersededBody",
    tone: "neutral",
    live: false,
  },
};

export const waitView = (wait: CompileWait): WaitView => VIEWS[wait.reason];

/** Оценка ожидания: секунды до минуты, дальше округляем вверх до минут. */
export const hintParts = (
  seconds: number,
): { unit: "s" | "m"; value: number } =>
  seconds < 60
    ? { unit: "s", value: Math.max(1, Math.round(seconds)) }
    : { unit: "m", value: Math.ceil(seconds / 60) };
