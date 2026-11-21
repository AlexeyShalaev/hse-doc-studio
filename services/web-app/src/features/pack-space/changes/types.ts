import type { PackVersionRef } from "@entities/pack-studio";

// Всё, что экран должен знать о работе человека (pack-studio-ux.md, 4.3). Тип общий для S3
// (`useChangesStatus`, панель «Изменения») и S4 (`resolveNextStep`, главная кнопка): менять поля
// можно только вместе. Это данные, а не тексты: слова подбирают потребители.
//
// Как читать. Статус собирается из ответов сервера чистой функцией `deriveChangesStatus`
// (`deriveChangesStatus.ts`, там же таблица правил), поэтому его можно проверять таблицей, а не
// кликами. Пока данные не пришли (`load !== "ready"`), остальные поля это «ничего не изменено»:
// главную кнопку в это время не показываем и «Править копию» не предлагаем.

/**
 * Что говорят проверки хостинга об открытом запросе. `unknown`: хостинг не отдаёт статус этому
 * токену, проверок у репозитория нет или ответ ещё не пришёл. Это не «идут» и не «прошли».
 */
export type ChangesChecks =
  "pending" | "passed" | "failed" | "awaiting_approval" | "unknown";

/**
 * Запрос на слияние (PR, MR) пространства. `label` это «#412» (GitHub и прочие) или «!412»
 * (GitLab): подставляется в тексты как есть, слово «запрос» добавляет потребитель.
 */
export type ChangesRequest =
  | { kind: "none" }
  | {
      kind: "open";
      number: number;
      label: string;
      url: string | null;
      checks: ChangesChecks;
      /** Сколько проверок хостинга завершилось из скольких; `null`, пока список неизвестен. */
      progress: { done: number; total: number } | null;
      /** После отправки запроса были новые правки: их можно добавить в тот же запрос. */
      newEdits: boolean;
    }
  | { kind: "merged"; number: number; label: string }
  | { kind: "closed"; number: number; label: string };

export type ChangesStatus = {
  /**
   * Состояние самих данных. `loading`: git ещё читается; `failed`: не прочитался (панель
   * покажет причину и повтор). Только при `ready` остальные поля настоящие.
   */
  load: "loading" | "ready" | "failed";
  /** Состояние подключения: клонируется, не удалось, готово. */
  connection: "cloning" | "failed" | "ready";
  /** Git или папка на диске (в папке запросов и главной кнопки нет, изменений не считаем). */
  workspaceKind: "git" | "folder";
  /** Открытая версия выпущена (замок). */
  released: boolean;
  /**
   * Сколько файлов во всём пространстве изменено относительно основной ветки (коммиты и правки
   * на диске). Это число на кнопке «Изменения»; `0`: кнопка без числа.
   */
  changedFiles: number;
  /** Из них лежит в каталоге открытой версии. */
  changedInVersion: number;
  /**
   * Другая версия, где у человека есть изменения (не открытая): сначала черновики, из них самая
   * новая. `null`, если все изменения в открытой версии или их нет совсем.
   */
  changedElsewhere: PackVersionRef | null;
  /**
   * Ошибки проверки, они блокируют отправку: по всем изменённым версиям, но не больше трёх
   * версий. Нехватка заметок к версии сюда не входит (см. `notesNeeded`).
   */
  errors: number;
  /** Замечания к оформлению, отправке не мешают. */
  warnings: number;
  /**
   * Открытая версия это черновик с правками, а заметок «что изменилось» (ru и en) в ней нет.
   * Ожидаемый шаг («Описать изменения»), а не ошибка.
   */
  notesNeeded: boolean;
  request: ChangesRequest;
  /** На сколько коммитов основная ветка ушла вперёд. Для папки всегда 0. */
  behind: number;
};

/** Ничего не изменено, запроса нет: состояние, с которого начинают потребители и тесты. */
export const NO_CHANGES: ChangesStatus = {
  load: "ready",
  connection: "ready",
  workspaceKind: "git",
  released: false,
  changedFiles: 0,
  changedInVersion: 0,
  changedElsewhere: null,
  errors: 0,
  warnings: 0,
  notesNeeded: false,
  request: { kind: "none" },
  behind: 0,
};
