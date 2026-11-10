import { createContext, useContext } from "react";
import type { GuardTarget, HeldDoc } from "../lib/editGuard";

/**
 * Мягкое предупреждение правки (docs/design/signing-route.md, 12.7). Места правки спрашивают
 * перед первым изменением документа, который держит идущий маршрут; ответ помнится на сеанс
 * для документа, маршрута и раунда.
 */
export type RouteEditGuard = {
  /** Маршруты проекта загружены (или спрашивать не нужно): решение «спросить» окончательное. */
  ready: boolean;
  /** Документы на подписании без ответа, которые задевает действие. Синхронно, для фильтров. */
  pending: (target: GuardTarget) => HeldDoc[];
  /** Названия всех документов на подписании, которые задевает действие (строка в плане). */
  heldNames: (target: GuardTarget) => string[];
  /** Спросить, если нужно: true, когда можно менять. */
  confirm: (target: GuardTarget) => Promise<boolean>;
  /**
   * Выполнить действие: сразу, если спрашивать не о чем (синхронно, как без предупреждения),
   * иначе после «Продолжить». «Отмена» действие не выполняет.
   */
  run: (target: GuardTarget, action: () => void) => void;
  /** Запомнить ответ без окна: автор видел предупреждение в другом месте (план обновления). */
  acknowledge: (target: GuardTarget) => void;
};

export type GuardScope = RouteEditGuard & { projectId: string };

const NO_GUARD: RouteEditGuard = {
  ready: true,
  pending: () => [],
  heldNames: () => [],
  confirm: () => Promise.resolve(true),
  run: (_target, action) => {
    action();
  },
  acknowledge: () => undefined,
};

export const GuardContext = createContext<GuardScope | null>(null);

/**
 * Предупреждение для правки проекта. Вне `RouteEditGuardProvider` этого проекта (локальная
 * Студия, гость, тесты отдельных мест) не спрашивает ничего.
 */
export const useRouteEditGuard = (projectId: string): RouteEditGuard => {
  const scope = useContext(GuardContext);
  return scope?.projectId === projectId ? scope : NO_GUARD;
};
