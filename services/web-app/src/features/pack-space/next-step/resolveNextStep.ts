import type { PackVersionRef } from "@entities/pack-studio";
import type { ChangesChecks, ChangesStatus } from "../changes/types";

// Главная кнопка полосы пространства (pack-studio-ux.md, 4.3): чистая функция от `ChangesStatus`,
// поэтому её проверяет таблица тестов, а не клики. Кнопка называет следующий шаг, а не «общую
// операцию»; что она делает, решает `NextStepButton`.
//
// Приоритет сверху вниз, срабатывает первая подходящая строка (номера строк таблицы 4.3 в
// скобках). Отличия от буквы таблицы, все ради того, чтобы кнопка не обманывала:
//  - папка на диске (11) разбирается сразу после подключения: «Править копию» там нет, главной
//    кнопки для папки нет по критерию среза;
//  - принятый запрос (10) идёт раньше выпущенной версии (3): после слияния версия как раз
//    выпущена, а «Начать новую правку» важнее «Править копию» поверх уже слитой ветки;
//  - у выпущенной версии строки 3 и 4 смотрят и на сам запрос: версия, которую человек выпустил
//    в своей ветке и отправил, «выпущена», но у неё есть свои изменения и открытый запрос.

export type NextStep =
  /** (1) Пространство подключается: кнопки нет, только подпись. */
  | { kind: "connecting" }
  /** (2) Подключение не удалось. */
  | { kind: "checkAccess" }
  /** (11) Папка на диске: кнопки нет, чип «Записано в папку». */
  | { kind: "folder" }
  /** (3) Выпущенная версия без своих изменений. */
  | { kind: "makeCopy" }
  /** (4) Выпущенная версия, свои изменения в другой. */
  | { kind: "toDraft"; version: PackVersionRef }
  /** (5) Есть ошибки проверки. */
  | { kind: "fixErrors"; count: number }
  /** (6) Нет заметок к версии. */
  | { kind: "describe" }
  /** (7) Всё готово к отправке. */
  | { kind: "submit" }
  /** (8) Запрос открыт, новых правок нет (вторичная кнопка). */
  | {
      kind: "request";
      label: string;
      checks: ChangesChecks;
      progress: { done: number; total: number } | null;
    }
  /** (9) Запрос открыт, есть новые правки. */
  | { kind: "updateRequest" }
  /** (10) Запрос принят. */
  | { kind: "startNew" };

/** Вторичные шаги не залиты акцентом: на экране главная кнопка одна. */
export const isPrimaryStep = (step: NextStep): boolean =>
  step.kind !== "request" &&
  step.kind !== "connecting" &&
  step.kind !== "folder";

/** Шаг есть кнопка (а не подпись или чип). */
export const isButtonStep = (step: NextStep): boolean =>
  step.kind !== "connecting" && step.kind !== "folder";

export const resolveNextStep = (status: ChangesStatus): NextStep | null => {
  if (status.connection === "cloning") return { kind: "connecting" };
  if (status.connection === "failed") return { kind: "checkAccess" };
  if (status.workspaceKind === "folder") return { kind: "folder" };
  // Пока git не прочитан, главную кнопку не показываем (см. `ChangesStatus.load`).
  if (status.load !== "ready") return null;
  const { request } = status;
  if (request.kind === "merged") return { kind: "startNew" };

  if (status.released) {
    if (status.changedFiles === 0 && request.kind !== "open") {
      return { kind: "makeCopy" };
    }
    if (status.changedInVersion === 0 && status.changedElsewhere) {
      return { kind: "toDraft", version: status.changedElsewhere };
    }
  }
  if (status.errors > 0) return { kind: "fixErrors", count: status.errors };
  if (status.notesNeeded) return { kind: "describe" };
  if (request.kind === "open") {
    return request.newEdits
      ? { kind: "updateRequest" }
      : {
          kind: "request",
          label: request.label,
          checks: request.checks,
          progress: request.progress,
        };
  }
  if (status.changedFiles > 0) return { kind: "submit" };
  // (12) Черновик, правок ещё нет: кнопки нет, редактируйте сразу.
  return null;
};
