import { createContext, useContext } from "react";
import type {
  RuleChange,
  RuleFormContext,
  RuleShape,
} from "@features/pack-forms/rule";
import type { DeltaItem } from "../../lib/edit/delta";
import type { History } from "../../lib/edit/history";
import type { RuleEdit } from "../../lib/edit/plan";

/** Запись, которую правит мини-форма. */
export type EditTarget = {
  /** Манифест от каталога версии. */
  file: string;
  /** Указатель записи правила. */
  pointer: string;
  shape: RuleShape;
  /** Вид решения (`slot_when`, `skip_if_nda` и т.п.): по нему подписывается запись в ленте. */
  kind: string;
};

/** Что не удалось или о чём автора предупреждаем: слова даёт экран, причина приходит с сервера. */
export type EditNotice =
  | { source: "form" | "history"; kind: "stale" }
  | { source: "form" | "history"; kind: "missing" }
  | { source: "form" | "history"; kind: "error"; error: unknown }
  // Запись изменилась после правки: откат или повтор перезапишут чужие изменения.
  | { source: "history"; kind: "drift"; direction: "undo" | "redo" };

export type EditDelta = {
  items: readonly DeltaItem[];
  /** Какая правка вызвала пересчёт: для заголовка. */
  edit: RuleEdit;
  direction: "apply" | "undo" | "redo";
};

/**
 * Правка по месту экрана «Результат»: запись теми же точечными правками YAML, что у вкладки
 * «Форма», стек отката и повтора, мягкое удаление, дельта результата после записи. Экран
 * условий пака не считает: после записи сервер пересчитывает результат, а здесь он сравнивается
 * с прежним.
 */
export type RuleEditUi = {
  /** Правка вообще предлагается: не телефон и не режим «Как студент». */
  available: boolean;
  /** Правка запрещена: выпущенная версия, не рабочее дерево или реестр. */
  blocked: "released" | "state" | "registry" | null;
  /** Модель версии загружена: мини-форму можно показать. */
  ready: boolean;
  loadFailed: unknown;
  /** Запись ушла на сервер. */
  busy: boolean;
  /** Начать загрузку модели версии (по первому «Править правило»). */
  begin: () => void;
  /** Данные манифеста для формы. */
  data: (file: string) => unknown;
  formContext: RuleFormContext;
  change: (target: EditTarget, change: RuleChange) => Promise<boolean>;
  /** Убрать условие или запись правила с отменой на десять секунд. */
  remove: (
    target: EditTarget,
    scope: "condition" | "record",
  ) => Promise<boolean>;
  history: History;
  canUndo: boolean;
  canRedo: boolean;
  undo: () => void;
  redo: () => void;
  /** Откат или повтор вопреки предупреждению о чужих изменениях. */
  force: (direction: "undo" | "redo") => void;
  notice: EditNotice | null;
  clearNotice: () => void;
  delta: EditDelta | null;
  dismissDelta: () => void;
  /** Ключи `раздел:id` элементов, которые только что изменились (подсветка на несколько секунд). */
  flashed: ReadonlySet<string>;
};

export const RuleEditContext = createContext<RuleEditUi | null>(null);

/** Правка экрана; вне экрана «Результат» её нет. */
export const useRuleEdit = (): RuleEditUi | null => useContext(RuleEditContext);
