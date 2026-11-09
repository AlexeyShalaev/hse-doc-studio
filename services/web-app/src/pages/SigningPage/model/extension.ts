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
  /**
   * Отпечатки для запроса, если блок только что сам изменил задачу (задал плашку) и
   * отпечатки показа устарели; не заданы: отпечатки последнего показа.
   */
  expected?: Record<string, string>;
};

/** Что страница даёт блокам подписи: задача, занятость и действия с отпечатками последнего показа. */
export type SigningSlotContext = {
  projectId: string;
  routeId: string;
  task: SigningTask;
  /** Действие на странице уже идёт: кнопки заняты. */
  busy: boolean;
  /** Код отказа последнего действия страницы (`failure.*`): окно пароля показывает его у себя. */
  failure: string | null;
  /** `expected` для запросов, которые блок шлёт сам (картинка, плашка, готовая подпись). */
  expected: Record<string, string>;
  /**
   * Согласовать. Ответ: новая задача или null при отказе (страница уже показала его
   * и перечитала задачу), чтобы блок мог продолжить цепочку: согласие, затем подпись.
   */
  approve: (options?: ApproveOptions) => Promise<SigningTask | null>;
  /** «Подписать» итоговый PDF ключом Студии (`next_action` = `sign`). */
  sign: (
    key: SigningKeyRequest,
    expected?: Record<string, string>,
  ) => Promise<SigningTask | null>;
};

/**
 * Точка расширения: подпись на странице (картинка, ЭП, КриптоПро, готовая подпись) из фичи
 * `signing-inline`. Страница сама показывает задачу, ход маршрута, документы, «Согласовать» и
 * «Вернуть на доработку»; функция, вернувшая null, оставляет поведение страницы.
 */
export type SigningExtension = {
  /** Блок «Как подписать»: способ, картинка, ключ. Без него страница показывает способ и готовность. */
  method?: (ctx: SigningSlotContext) => ReactNode;
  /** Главная кнопка. Без неё страница рисует «Согласовать» для `approve`. */
  primary?: (ctx: SigningSlotContext) => ReactNode;
};
