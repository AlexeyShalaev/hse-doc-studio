import {
  NO_REMOTE_STATUS,
  toStatusView,
  type GitCommitBrief,
  type GitStatus,
  type SyncStatusView,
} from "@entities/git-sync";
import { REMOTE } from "./statusFactory";

// Состояния синхронизации для галереи и для тестов: по одному на каждый вид,
// который видит человек. Время считается от «сейчас», поэтому подписи
// «3 часа назад» остаются живыми, сколько бы ни прошло со дня написания.

export type SyncStateFixture = {
  id: string;
  /** Название состояния: так его называют в разговоре о правках. */
  title: string;
  /** Что в нём главное. */
  note: string;
  /** Условия браузера и проекта, которые не приходят с сервера. */
  context?: { online?: boolean; readOnly?: boolean };
  /** Показывать ли полосу конфликтов (она видна только в этом состоянии). */
  banner?: boolean;
  build: (now: number) => SyncStatusView;
};

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

const ago = (now: number, ms: number): string =>
  new Date(now - ms).toISOString();

const PEOPLE = [
  { author: "Анна Петрова", author_email: "anna@edu.hse.ru" },
  { author: "Борис Лаптев", author_email: "boris@edu.hse.ru" },
  { author: "Иван Смирнов", author_email: "ivan@edu.hse.ru" },
] as const;

const MESSAGES = [
  "Дописала введение",
  "Правки по замечаниям научрука",
  "Обновил список литературы",
  "Новая глава: экспериментальная часть",
  "Исправил формулы в главе 2",
  "Заменил рисунок архитектуры",
];

const commits = (
  now: number,
  count: number,
  prefix: string,
  offset = 0,
): GitCommitBrief[] =>
  Array.from({ length: Math.min(count, 5) }, (_, index) => {
    const person = PEOPLE[(index + offset) % PEOPLE.length] ?? PEOPLE[0];
    const id = `${prefix}${String(index + 1)}c0ffee1234567890`;
    return {
      id,
      short_id: id.slice(0, 7),
      message:
        MESSAGES[(index + offset) % MESSAGES.length] ?? MESSAGES[0] ?? "",
      author: person.author,
      author_email: person.author_email,
      created_at: ago(now, (index + 1) * 47 * MINUTE + offset * HOUR),
      kind: "edit",
    };
  });

const base = (now: number, overrides: Partial<GitStatus>): SyncStatusView =>
  toStatusView({
    ...NO_REMOTE_STATUS,
    connected: true,
    ui_state: "up_to_date",
    remote: REMOTE,
    relation: "in_sync",
    last_fetch_at: ago(now, 4 * MINUTE),
    last_fetch_ok_at: ago(now, 4 * MINUTE),
    last_sync_at: ago(now, 3 * HOUR),
    last_sync: {
      id: "sync-seed",
      at: ago(now, 3 * HOUR),
      outcome: "merged",
      pulled_commits: 2,
      pushed_commits: 3,
    },
    auto_fetch: { enabled: true, interval_s: 300, next_fetch_at: null },
    ...overrides,
  });

const operation = (
  now: number,
  phase: string,
  percent: number | null,
  kind = "sync",
): GitStatus["operation"] => ({
  id: "op-gallery",
  kind,
  phase,
  percent,
  cancellable: phase !== "merge",
  started_at: ago(now, 20_000),
});

const diverged = (now: number, extra: Partial<GitStatus> = {}) =>
  base(now, {
    ui_state: "diverged",
    relation: "diverged",
    ahead: 3,
    behind: 2,
    behind_files: 5,
    incoming: commits(now, 2, "in"),
    outgoing: commits(now, 3, "out", 1),
    ...extra,
  });

const failed = (
  now: number,
  uiState: string,
  health: string,
  code: string,
  detail: string,
  extra: Partial<GitStatus> = {},
): SyncStatusView =>
  base(now, {
    ui_state: uiState,
    health,
    last_error: { code, detail, at: ago(now, 2 * MINUTE) },
    ahead: 2,
    relation: "ahead",
    outgoing: commits(now, 2, "out", 1),
    ...extra,
  });

const blocked = (
  now: number,
  reason: string,
  requiredStudio: string | null = null,
): SyncStatusView =>
  base(now, {
    ui_state: "blocked",
    blocked: { reason, required_studio: requiredStudio },
  });

export const SYNC_STATE_FIXTURES: SyncStateFixture[] = [
  {
    id: "no_remote",
    title: "Не подключено",
    note: "Кнопка приглушена, действие: «Подключить репозиторий».",
    build: () => toStatusView(NO_REMOTE_STATUS),
  },
  {
    id: "no_remote_read_only",
    title: "Не подключено, проект только для чтения",
    note: "Подключить нельзя: в панели пояснение, кнопка открывает подробности.",
    context: { readOnly: true },
    build: () => toStatusView(NO_REMOTE_STATUS),
  },
  {
    id: "unfetched",
    title: "Подключено, ещё не проверяли",
    note: "Репозиторий привязан, но обмена не было.",
    build: (now) =>
      base(now, {
        ui_state: "unfetched",
        relation: "unfetched",
        last_fetch_at: null,
        last_fetch_ok_at: null,
        last_sync_at: null,
        last_sync: null,
      }),
  },
  {
    id: "up_to_date",
    title: "Всё синхронизировано",
    note: "Рядом с названием время последней синхронизации.",
    build: (now) => base(now, {}),
  },
  {
    id: "ahead",
    title: "Есть неотправленное",
    note: "Стрелка вверх и число версий, которых нет в репозитории.",
    build: (now) =>
      base(now, {
        ui_state: "ahead",
        relation: "ahead",
        ahead: 4,
        outgoing: commits(now, 4, "out"),
      }),
  },
  {
    id: "behind",
    title: "Пришли чужие изменения",
    note: "Стрелка вниз; в панели список пришедших версий и сколько файлов затронуто.",
    build: (now) =>
      base(now, {
        ui_state: "behind",
        relation: "behind",
        behind: 3,
        behind_files: 7,
        incoming: commits(now, 3, "in"),
      }),
  },
  {
    id: "diverged",
    title: "И то и другое",
    note: "Есть и пришедшее, и неотправленное: нужно слияние.",
    build: (now) => diverged(now),
  },
  {
    id: "syncing_queued",
    title: "Синхронизация: в очереди",
    note: "Ждёт окончания сборки PDF; первый шаг помечен подсказкой.",
    build: (now) =>
      diverged(now, {
        ui_state: "syncing",
        operation: operation(now, "queued", null),
      }),
  },
  {
    id: "syncing_snapshot",
    title: "Синхронизация: сохраняем версию",
    note: "Список шагов с идущим первым шагом.",
    build: (now) =>
      diverged(now, {
        ui_state: "syncing",
        operation: operation(now, "snapshot", null),
      }),
  },
  {
    id: "syncing_fetch",
    title: "Синхронизация: получаем (40%)",
    note: "Процент на кнопке и у шага; доступна отмена.",
    build: (now) =>
      diverged(now, {
        ui_state: "syncing",
        operation: operation(now, "fetch", 40),
      }),
  },
  {
    id: "syncing_merge",
    title: "Синхронизация: объединяем",
    note: "Слияние нельзя отменить: кнопки отмены нет.",
    build: (now) =>
      diverged(now, {
        ui_state: "syncing",
        operation: operation(now, "merge", null),
      }),
  },
  {
    id: "syncing_push",
    title: "Синхронизация: отправляем (80%)",
    note: "Последний шаг.",
    build: (now) =>
      diverged(now, {
        ui_state: "syncing",
        operation: operation(now, "push", 80),
      }),
  },
  {
    id: "syncing_bundle",
    title: "Идёт импорт файла",
    note: "Операция не из синхронизации: в подписи её название.",
    build: (now) =>
      base(now, {
        ui_state: "syncing",
        operation: operation(now, "verify", null, "bundle_import"),
      }),
  },
  {
    id: "conflicts",
    title: "Конфликты",
    note: "Красная кнопка с числом файлов, действие: «Решить конфликты»; вверху экрана полоса.",
    banner: true,
    build: (now) =>
      diverged(now, {
        ui_state: "conflicts",
        pending: { session_id: "session-1", files_total: 6, files_open: 2 },
      }),
  },
  {
    id: "auth_failed",
    title: "Доступ не принят",
    note: "Токен отозван или истёк; действие: «Обновить доступ».",
    build: (now) =>
      failed(
        now,
        "auth_failed",
        "unauthenticated",
        "auth_failed",
        "Remote: Invalid username or token. Password authentication is not supported.",
      ),
  },
  {
    id: "offline",
    title: "Репозиторий недоступен",
    note: "Сервер не отвечает; действие: «Проверить ещё раз».",
    build: (now) =>
      failed(
        now,
        "offline",
        "offline",
        "offline",
        "Could not resolve host: github.com",
      ),
  },
  {
    id: "offline_browser",
    title: "Нет сети на этом компьютере",
    note: "Состояние считается в браузере: синхронизация не запускается.",
    context: { online: false },
    build: (now) => base(now, {}),
  },
  {
    id: "error_remote_moved",
    title: "Ошибка: репозиторий изменился во время отправки",
    note: "Красная заметка с причиной и свёрнутые технические подробности.",
    build: (now) =>
      failed(
        now,
        "error",
        "error",
        "remote_moved",
        "non-fast-forward after 3 attempts",
      ),
  },
  {
    id: "error_large_file",
    title: "Ошибка: файл слишком велик",
    note: "Другая причина, тот же вид; подсказка называет файл.",
    build: (now) =>
      failed(
        now,
        "error",
        "error",
        "large_file",
        "video/defense-rehearsal.mov is 187.00 MB; this exceeds GitHub's file size limit of 100.00 MB",
      ),
  },
  {
    id: "error_push_rejected",
    title: "Ошибка: сервер Студии отклонил отправку",
    note: "Pre-receive сервера HSE Doc Studio: блок «Сервер отклонил отправку» с перечнем нарушений.",
    build: (now) =>
      failed(
        now,
        "error",
        "error",
        "push_rejected",
        "Сервер отклонил отправку: изменения нарушают правила проекта:\n- petrov/main.tex: вне вашей папки в командном проекте [path_outside_scope]\n- assets/logo.lnk: символьные ссылки не принимаются [symlink]",
      ),
  },
  {
    id: "error_unknown",
    title: "Ошибка без названия",
    note: "Незнакомый код: общий текст и техническая строка.",
    build: (now) =>
      failed(now, "error", "error", "git_error", "fatal: unable to read tree"),
  },
  {
    id: "blocked_off_branch",
    title: "Заблокировано: другая ветка",
    note: "В проекте переключена ветка, не та, что связана с репозиторием.",
    build: (now) => blocked(now, "off_branch"),
  },
  {
    id: "blocked_read_only",
    title: "Заблокировано: только чтение",
    note: "Проект открыт на чтение: отправлять нельзя.",
    build: (now) => blocked(now, "read_only"),
  },
  {
    id: "blocked_schema_newer",
    title: "Заблокировано: нужна новая Студия",
    note: "Проект записан более новой версией; в тексте нужная версия.",
    build: (now) => blocked(now, "remote_schema_newer", "0.4.0"),
  },
  {
    id: "blocked_store_untrusted",
    title: "Заблокировано: хранилище не доверено",
    note: "Папку версий скопировали с другого компьютера.",
    build: (now) => blocked(now, "store_untrusted"),
  },
  {
    id: "blocked_profile_required",
    title: "Заблокировано: нет автора версий",
    note: "Надо представиться; кнопка ведёт в окно профиля.",
    build: (now) => blocked(now, "profile_required"),
  },
  {
    id: "shared_folder",
    title: "Папка в облачной синхронизации",
    note: "Предупреждение про Яндекс Диск и подтверждение.",
    build: (now) =>
      base(now, {
        shared_folder: {
          provider: "yandex_disk",
          root: "/Users/ivan/Yandex.Disk",
          acknowledged: false,
        },
      }),
  },
  {
    id: "unknown",
    title: "Состояние от более новой Студии",
    note: "Сервер прислал неизвестное значение: нейтральный вид и подсказка обновиться.",
    build: (now) => base(now, { ui_state: "future_state" }),
  },
];
