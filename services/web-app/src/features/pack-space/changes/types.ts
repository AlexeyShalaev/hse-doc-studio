import type { PackVersionRef } from "@entities/pack-studio";

// Всё, что экран должен знать о работе человека (pack-studio-ux.md, 4.3). Тип общий для S3
// (`useChangesStatus`, панель «Изменения») и S4 (`resolveNextStep`, главная кнопка): менять поля
// можно только вместе. Это данные, а не тексты: слова подбирают потребители.

/** Запрос на слияние (PR, MR) пространства. */
export type ChangesRequest =
  | { kind: "none" }
  | {
      kind: "open";
      number: number;
      url: string | null;
      /** Проверки на хостинге: идут, прошли, не прошли, ждут одобрения мейнтейнера. */
      checks: "pending" | "passed" | "failed" | "awaiting_approval";
      /** После отправки запроса были новые правки. */
      newEdits: boolean;
    }
  | { kind: "merged"; number: number }
  | { kind: "closed"; number: number };

export type ChangesStatus = {
  /** Состояние подключения: клонируется, не удалось, готово. */
  connection: "cloning" | "failed" | "ready";
  /** Git или папка на диске (в папке запросов и главной кнопки нет). */
  workspaceKind: "git" | "folder";
  /** Открытая версия выпущена (замок). */
  released: boolean;
  /** Сколько файлов изменено относительно основной ветки. */
  changedFiles: number;
  /** Версия, где у человека есть изменения, если это не открытая версия. */
  changedElsewhere: PackVersionRef | null;
  /** Ошибки проверки блокируют отправку; замечания нет. Нехватка заметок сюда не входит. */
  errors: number;
  warnings: number;
  /** Для новой версии нужны заметки «что изменилось»: ожидаемый шаг, не ошибка. */
  notesNeeded: boolean;
  request: ChangesRequest;
  /** На сколько коммитов основная ветка ушла вперёд. */
  behind: number;
};

/** Ничего не изменено, запроса нет: состояние `none`, с которого начинают потребители. */
export const NO_CHANGES: ChangesStatus = {
  connection: "ready",
  workspaceKind: "git",
  released: false,
  changedFiles: 0,
  changedElsewhere: null,
  errors: 0,
  warnings: 0,
  notesNeeded: false,
  request: { kind: "none" },
  behind: 0,
};
