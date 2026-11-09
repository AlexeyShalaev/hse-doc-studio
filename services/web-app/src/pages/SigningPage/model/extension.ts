import type { ReactNode } from "react";
import type {
  RouteSignMethod,
  SigningKeyRequest,
  SigningTask,
} from "@entities/signing-route";

/** «Согласовать» с выбором способа и «Согласовать и подписать» (ключ Студии и пароль). */
export type ApproveOptions = {
  /** Сменить способ своих слотов (из `me.methods`); не задан: оставить. */
  method?: RouteSignMethod | null;
  /** Подписать свои криптослоты в том же запросе (`next_action` = `approve_and_sign`). */
  sign?: SigningKeyRequest | null;
};

/** Что страница даёт блокам подписи: задача, занятость и действия с отпечатками последнего показа. */
export type SigningSlotContext = {
  projectId: string;
  routeId: string;
  task: SigningTask;
  /** Действие на странице уже идёт: кнопки заняты. */
  busy: boolean;
  /** `expected` для запросов, которые блок шлёт сам (картинка, плашка, готовая подпись). */
  expected: Record<string, string>;
  approve: (options?: ApproveOptions) => void;
  /** «Подписать» итоговый PDF ключом Студии (`next_action` = `sign`). */
  sign: (key: SigningKeyRequest) => void;
};

/**
 * Точка расширения для среза W5 (подпись на странице: картинка, ЭП, КриптоПро, готовая подпись).
 * Страница сама показывает задачу, ход маршрута, документы, «Согласовать» и «Вернуть на доработку».
 * W5 передаёт сюда свои блоки из фичи; функция, вернувшая null, оставляет поведение страницы.
 */
export type SigningExtension = {
  /** Блок «Как подписать»: способ, картинка, ключ. Без него страница показывает способ и готовность. */
  method?: (ctx: SigningSlotContext) => ReactNode;
  /**
   * Главная кнопка. Без неё страница рисует «Согласовать» для `approve`, а для
   * `approve_and_sign` и `sign` только заглушку в блоке «Как подписать».
   */
  primary?: (ctx: SigningSlotContext) => ReactNode;
};
