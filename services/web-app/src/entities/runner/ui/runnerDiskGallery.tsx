import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import {
  DISK_OWNER,
  DISK_RUNNER_VERSION,
  RUNNER_DISK_STATES,
  type RunnerDiskStateId,
} from "../testing/fixtures";
import { RunnerDiskDialogPreview } from "./RunnerDiskDialogPreview";
import { RunnerDiskPanel, type RunnerDiskPanelProps } from "./RunnerDiskPanel";

// Галерея панели «Диск» (docs/design/storage-cleanup.md, 4.5): каждое состояние 4.1 на
// эталонах RUNNER_DISK_STATES. Экраны W4–W6 берут отсюда runnerDiskGalleryEntry для своих
// разделов («Раннеры: диск», «Мои раннеры: диск»).

const W = 640;
const PHONE = 390;
const noop = () => undefined;

const NAME = "build-01";

/** Запись галереи с панелью в рамке окна «Диск». */
export const runnerDiskGalleryEntry = (
  id: string,
  title: string,
  state: RunnerDiskStateId,
  props: Partial<RunnerDiskPanelProps> = {},
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: W,
  render: () => (
    <RunnerDiskPanel
      view={RUNNER_DISK_STATES[state]}
      runnerName={state.startsWith("personal") ? "MacBook Марии" : NAME}
      runnerVersion={DISK_RUNNER_VERSION}
      onRefresh={noop}
      onClean={noop}
      onCancel={noop}
      {...props}
    />
  ),
  ...extra,
});

const STATES: [RunnerDiskStateId, string, string?][] = [
  ["docker", "Docker-раннер с полным замером"],
  [
    "nothing_to_clean",
    "Нечего освобождать",
    "Кнопки выключены, «Очистить всё» тоже.",
  ],
  ["measuring", "Нажали «Обновить»: идёт замер"],
  ["waiting", "Ждём раннер", "Команда ещё не забрана, можно отменить."],
  ["running", "Идёт очистка: шаг 3 из 9"],
  ["cancelling", "Останавливается после текущего шага"],
  ["cancelled", "Остановлено", "Итог можно скрыть крестиком."],
  ["done", "Итог: освобождено", "Раннер уже прислал новый замер."],
  ["done_nothing", "Итог: освобождать было нечего"],
  ["done_error", "Итог с ошибками", "Шаги с причиной из Docker."],
  ["expired", "Команда не забрана за 10 минут"],
  ["lost", "Раннер пропал во время очистки"],
  ["offline", "Раннер не на связи", "Последний замер, кнопки выключены."],
  ["no_report", "Замера ещё нет"],
  ["stale", "Замер старше суток"],
  ["docker_unavailable", "Docker недоступен", "Работает только кэш раннера."],
  ["kubernetes", "Раннер в Kubernetes", "Только кэш раннера и том данных."],
  ["desktop", "Локальная Студия", "Docker этого компьютера чистится в Студии."],
  [
    "personal_admin",
    "Личный раннер глазами админа",
    "Плашка владельца, отката нет.",
  ],
  ["personal_owner", "Свой раннер в «Моих раннерах»"],
  ["personal_owner_done", "Свой раннер после очистки админом"],
];

/** Все записи панели «Диск»: состояния, подтверждения, телефон. */
export const runnerDiskGalleryEntries = (): GalleryEntry[] => [
  ...STATES.map(([state, title, note]) =>
    runnerDiskGalleryEntry(
      `disk_${state}`,
      title,
      state,
      {},
      note ? { note } : {},
    ),
  ),
  runnerDiskGalleryEntry(
    "disk_outdated_upgrade",
    "Старая версия, установлен из админки",
    "outdated",
    { onUpgrade: noop },
    { note: "Кнопка «Обновить раннер», как в «Как развёрнут»." },
  ),
  runnerDiskGalleryEntry(
    "disk_outdated",
    "Старая версия, поставлен вручную",
    "outdated",
  ),
  runnerDiskGalleryEntry("disk_failure", "Отказ сервера", "docker", {
    error: "Раннер не на связи. Очистить диск можно, когда он вернётся.",
  }),
  runnerDiskGalleryEntry(
    "disk_confirm_all",
    "Подтверждение «Очистить всё»",
    "docker",
    { initialConfirm: "all" },
  ),
  runnerDiskGalleryEntry(
    "disk_confirm_old_rollback",
    "Старые версии с флажком отката",
    "docker",
    { initialConfirm: "old_versions", initialIncludeRollback: true },
    { note: "Флажок видит админ общего раннера и владелец личного." },
  ),
  runnerDiskGalleryEntry(
    "disk_confirm_old_personal_admin",
    "Старые версии личного раннера у админа",
    "personal_admin",
    { initialConfirm: "old_versions" },
    { note: `Флажка нет: откат удаляет только ${DISK_OWNER.name}.` },
  ),
  runnerDiskGalleryEntry(
    "disk_confirm_unused",
    "Подтверждение неиспользуемых образов",
    "docker",
    { initialConfirm: "unused_images" },
  ),
  runnerDiskGalleryEntry(
    "disk_confirm_runner_cache",
    "Подтверждение кэша раннера в Kubernetes",
    "kubernetes",
    { initialConfirm: "runner_cache" },
  ),
  runnerDiskGalleryEntry(
    "disk_phone_docker",
    "Телефон: полный замер",
    "docker",
    {},
    { width: PHONE },
  ),
  runnerDiskGalleryEntry(
    "disk_phone_confirm",
    "Телефон: старые версии с откатом",
    "docker",
    { initialConfirm: "old_versions", initialIncludeRollback: true },
    { width: PHONE },
  ),
  runnerDiskGalleryEntry(
    "disk_phone_running",
    "Телефон: идёт очистка",
    "running",
    {},
    { width: PHONE },
  ),
  {
    id: "disk_dialog",
    title: "Окно «Диск» целиком",
    note: "На телефоне окно становится шторкой снизу.",
    frame: "plain",
    render: () => (
      <RunnerDiskDialogPreview
        view={RUNNER_DISK_STATES.docker}
        runnerName={NAME}
      />
    ),
  },
];

/** Раздел галереи серверных экранов: панель «Диск» раннера без экрана вокруг. */
export const getRunnerDiskGallery = (): GalleryGroup[] => [
  {
    id: "runner-disk",
    title: "Раннеры: диск",
    description:
      "Окно «Диск» раннера: замер по категориям, блоки очистки, подтверждения, ход и итог. Одно и то же окно открывают админка и «Мои раннеры».",
    entries: runnerDiskGalleryEntries(),
  },
];
