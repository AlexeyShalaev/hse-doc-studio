import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import type { CompilePlacement, ProjectBuildRunners } from "@entities/runner";
import type { CompileWait } from "@entities/session";
import type { PlacementPerspective } from "../lib/placementView";
import { BuildPlacementChip } from "./BuildPlacementChip";
import { CompileWaitNotice } from "./CompileWaitNotice";
import { EditorBusyView } from "./EditorBusyView";
import { ProjectBuildsCard } from "./ProjectBuildsCard";
import { ProjectBuildsView } from "./ProjectBuildsView";

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

const placed = (extra: Partial<CompilePlacement> = {}): CompilePlacement => ({
  state: "shared",
  runner_name: null,
  runner_owner: null,
  fallback: null,
  wait_s: null,
  ...extra,
});

const chip = (
  id: string,
  title: string,
  placement: CompilePlacement,
  perspective: PlacementPerspective = "me",
): GalleryEntry => ({
  id,
  title,
  frame: "plain",
  width: 560,
  render: () => (
    <BuildPlacementChip placement={placement} perspective={perspective} />
  ),
});

const BUILDS: ProjectBuildRunners = {
  policy: "shared",
  editable: true,
  project_kind: "personal",
  personal_runners_enabled: true,
  my_builds: "personal_first",
  wait_s: 5,
  owner_runners: [
    { name: "MacBook Анны", state: "online" },
    { name: "Домашний сервер", state: "paused" },
  ],
};

const builds = (
  id: string,
  title: string,
  extra: Partial<ProjectBuildRunners> = {},
  status: "loading" | "error" | "ready" = "ready",
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: 620,
  render: () => (
    <ProjectBuildsView
      status={status}
      info={{ ...BUILDS, ...extra }}
      onChange={noop}
      onRetry={noop}
    />
  ),
});

/** Состояния сборки и занятого редактора (галерея /dev/server-screens). */
export const getBuildStatesGallery = (): GalleryGroup[] => [
  {
    id: "build-placement",
    title: "Сборка: где идёт",
    description:
      "Чип в шапке лога: свой раннер, раннер владельца, общий и фолбэк с причиной.",
    entries: [
      chip(
        "waiting_me",
        "Ждём ваш раннер",
        placed({
          state: "waiting_personal",
          runner_name: "MacBook Анны",
          runner_owner: "me",
          wait_s: 5,
        }),
      ),
      chip(
        "waiting_owner",
        "Соавтор: ждём раннер владельца",
        placed({
          state: "waiting_personal",
          runner_name: "Десктоп Павла",
          runner_owner: "owner",
          wait_s: 5,
        }),
      ),
      chip(
        "personal_me",
        "На вашем раннере",
        placed({
          state: "personal",
          runner_name: "MacBook Анны",
          runner_owner: "me",
        }),
      ),
      chip(
        "personal_owner",
        "Соавтор: на раннере владельца",
        placed({
          state: "personal",
          runner_name: "Десктоп Павла",
          runner_owner: "owner",
        }),
      ),
      chip("shared", "На общем раннере", placed()),
      chip(
        "fallback_offline",
        "Фолбэк: раннер не в сети",
        placed({ fallback: "offline" }),
      ),
      chip(
        "fallback_busy",
        "Фолбэк: раннер занят",
        placed({ fallback: "busy" }),
      ),
      chip(
        "fallback_timeout",
        "Фолбэк: не взял за 5 с",
        placed({ fallback: "timeout", wait_s: 5 }),
      ),
      chip(
        "fallback_lost",
        "Фолбэк: пропал посреди сборки",
        placed({ fallback: "lost" }),
      ),
      chip(
        "fallback_disabled",
        "Фолбэк: личные выключены",
        placed({ fallback: "disabled" }),
      ),
      chip(
        "fallback_owner",
        "Соавтор: раннер владельца не в сети",
        placed({ fallback: "offline" }),
        "owner",
      ),
    ],
  },
  {
    id: "project-builds",
    title: "Проект: сборки",
    description:
      "Раздел настроек проекта: владелец выбирает, где идут сборки соавторов; соавтор видит только чтение.",
    entries: [
      builds("owner_shared", "Владелец: на общих (по умолчанию)"),
      builds("owner_owner", "Владелец: на моих раннерах", { policy: "owner" }),
      builds("owner_none", "Владелец без своих раннеров", {
        owner_runners: [],
        my_builds: "shared",
      }),
      builds("coauthor_owner", "Соавтор: на раннере владельца", {
        policy: "owner",
        editable: false,
        owner_runners: [{ name: "Десктоп Павла", state: "online" }],
      }),
      builds("coauthor_shared", "Соавтор: на общих", {
        editable: false,
        my_builds: "shared",
      }),
      builds("org", "Проект организации", {
        project_kind: "org",
        editable: false,
        owner_runners: [],
        my_builds: "shared",
      }),
      builds("disabled", "Личные раннеры выключены", {
        personal_runners_enabled: false,
        my_builds: "shared",
        owner_runners: [{ name: "MacBook Анны", state: "disabled" }],
      }),
      builds("loading", "Загрузка", {}, "loading"),
      builds("error", "Не загрузилось", {}, "error"),
      {
        id: "live_owner",
        title: "Живой раздел: свой проект",
        frame: "window",
        width: 620,
        scenario: "runners_ready",
        render: () => <ProjectBuildsCard projectId="p_01hxa1c4de" />,
      },
      {
        id: "live_coauthor",
        title: "Живой раздел: проект Павла",
        frame: "window",
        width: 620,
        scenario: "runners_ready",
        render: () => <ProjectBuildsCard projectId="p_01hxa3k2jm" />,
      },
    ],
  },
  {
    id: "build-wait",
    title: "Сборка: ожидание",
    description: "Плашка над логом, пока сборка не идёт.",
    entries: [
      notice(
        "build_personal_runner",
        "Ждём личный раннер",
        wait("personal_runner", { wait_hint_seconds: 5 }),
        { note: "Окно ожидания личного раннера перед общими." },
      ),
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
