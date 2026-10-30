import type { GalleryGroup } from "@shared/lib/stateGallery";
import type { CompileWait } from "@entities/session";
import { CompileWaitNotice } from "./CompileWaitNotice";
import { EditorBusyView } from "./EditorBusyView";

const noop = () => undefined;

const wait = (
  reason: CompileWait["reason"],
  extra: Partial<CompileWait> = {},
): CompileWait => ({
  reason,
  queue_position: null,
  wait_hint_seconds: null,
  attempt: null,
  max_attempts: null,
  ...extra,
});

const notice = (
  id: string,
  title: string,
  w: CompileWait,
  extra: { note?: string; finished?: boolean } = {},
) => ({
  id,
  title,
  ...(extra.note ? { note: extra.note } : {}),
  frame: "window" as const,
  width: 720,
  render: () => (
    <CompileWaitNotice
      wait={w}
      finished={extra.finished ?? false}
      onRetry={noop}
    />
  ),
});

/** Состояния сборки и занятого редактора (галерея /dev/server-screens). */
export const getBuildStatesGallery = (): GalleryGroup[] => [
  {
    id: "build-wait",
    title: "Сборка: ожидание",
    description: "Плашка над логом, пока сборка не идёт.",
    entries: [
      notice(
        "build_queued",
        "В очереди",
        wait("queued", { queue_position: 3, wait_hint_seconds: 45 }),
        { note: "Место и оценка ожидания." },
      ),
      notice(
        "build_queued_minutes",
        "В очереди, ждать минуты",
        wait("queued", { queue_position: 12, wait_hint_seconds: 260 }),
      ),
      notice(
        "build_queued_unknown",
        "В очереди, место неизвестно",
        wait("queued"),
      ),
      notice(
        "build_quota",
        "Ждём своей очереди",
        wait("quota_wait", { queue_position: 1, wait_hint_seconds: 20 }),
        { note: "У человека уже идут сборки до лимита." },
      ),
      notice(
        "build_no_runner",
        "Нет доступных раннеров",
        wait("no_runner", { queue_position: 1 }),
        { note: "Сборка ждёт; кнопки отмены в шапке." },
      ),
      notice(
        "build_no_runner_finished",
        "Нет раннеров, сборка завершена",
        wait("no_runner"),
        { finished: true, note: "Итог без сборки: кнопка повтора." },
      ),
      notice(
        "build_runner_lost",
        "Раннер потерян, повторяем",
        wait("runner_lost", { attempt: 2, max_attempts: 3 }),
      ),
      notice("build_superseded", "Заменена более новой", wait("superseded"), {
        finished: true,
        note: "Кнопка собрать заново.",
      }),
    ],
  },
  {
    id: "editor-busy",
    title: "Редактор документов занят",
    description: "Лимит одновременных сессий ONLYOFFICE исчерпан.",
    entries: [
      {
        id: "editor_busy_countdown",
        title: "Обратный отсчёт и скачивание",
        frame: "window",
        width: 720,
        render: () => (
          <EditorBusyView
            retryAfterSeconds={60}
            limit={18}
            onRetry={noop}
            downloadHref="#"
            downloadName="report.docx"
          />
        ),
      },
      {
        id: "editor_busy_ready",
        title: "Можно повторять",
        note: "Отсчёт закончился.",
        frame: "window",
        width: 720,
        render: () => (
          <EditorBusyView
            retryAfterSeconds={1}
            limit={18}
            onRetry={noop}
            downloadHref={null}
          />
        ),
      },
    ],
  },
];
