import type { CompilePlacement, PlacementFallback } from "@entities/runner";

/** Чей это раннер с точки зрения того, кто смотрит: свой или владельца проекта. */
export type PlacementPerspective = "me" | "owner";

export type PlacementTone = "ok" | "info" | "warn" | "neutral";

export type PlacementView = {
  /** Ключ в documents:compile.placement */
  key: string;
  params: Record<string, string | number>;
  tone: PlacementTone;
  kind: "waiting" | "personal" | "shared" | "fallback";
};

// Окно ожидания по умолчанию, если сервер его не прислал.
const DEFAULT_WAIT_S = 5;

const FALLBACK_TONE: Record<PlacementFallback, PlacementTone> = {
  offline: "warn",
  busy: "warn",
  timeout: "warn",
  lost: "warn",
  // Выключение админом не беда сборки: это решение установки.
  disabled: "neutral",
};

/**
 * Где идёт сборка, словами раздела 11.4 спецификации. Для соавтора «ваш
 * раннер» становится «раннером владельца»: runner_owner у ожидания и личного
 * раннера приходит с сервера, а у пометки фолбэка его нет, поэтому её сторону
 * знает тот, кто показывает (владелец проекта или соавтор).
 */
export const placementView = (
  placement: CompilePlacement,
  perspective: PlacementPerspective = "me",
): PlacementView => {
  const whose = placement.runner_owner ?? perspective;
  const name = placement.runner_name;
  if (placement.state === "waiting_personal") {
    const seconds = placement.wait_s ?? DEFAULT_WAIT_S;
    const base = whose === "me" ? "waitingMe" : "waitingOwner";
    return {
      key: name ? base : `${base}NoName`,
      params: name ? { name, seconds } : { seconds },
      tone: "info",
      kind: "waiting",
    };
  }
  if (placement.state === "personal") {
    const base = whose === "me" ? "personalMe" : "personalOwner";
    return {
      key: name ? base : `${base}NoName`,
      params: name ? { name } : {},
      tone: "ok",
      kind: "personal",
    };
  }
  if (placement.fallback) {
    return {
      key: `${perspective === "me" ? "fallbackMe" : "fallbackOwner"}.${placement.fallback}`,
      params: { seconds: placement.wait_s ?? DEFAULT_WAIT_S },
      tone: FALLBACK_TONE[placement.fallback],
      kind: "fallback",
    };
  }
  return { key: "shared", params: {}, tone: "neutral", kind: "shared" };
};
