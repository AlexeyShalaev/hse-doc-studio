import type { GalleryGroup } from "@shared/lib/stateGallery";
import { SyncStateSheet } from "./SyncStateSheet";
import { SYNC_STATE_FIXTURES } from "./syncStates";

const GROUPS: { id: string; title: string; ids: string[] }[] = [
  {
    id: "rest",
    title: "Подключение и покой",
    ids: ["no_remote", "no_remote_read_only", "unfetched", "up_to_date"],
  },
  {
    id: "changes",
    title: "Есть что обменять",
    ids: ["ahead", "behind", "diverged"],
  },
  {
    id: "running",
    title: "Идёт синхронизация",
    ids: [
      "syncing_queued",
      "syncing_snapshot",
      "syncing_fetch",
      "syncing_merge",
      "syncing_push",
      "syncing_bundle",
    ],
  },
  { id: "conflicts", title: "Конфликты", ids: ["conflicts"] },
  {
    id: "problems",
    title: "Проблемы",
    ids: [
      "auth_failed",
      "offline",
      "offline_browser",
      "error_remote_moved",
      "error_large_file",
      "error_unknown",
    ],
  },
  {
    id: "blocked",
    title: "Заблокировано",
    ids: [
      "blocked_off_branch",
      "blocked_read_only",
      "blocked_schema_newer",
      "blocked_store_untrusted",
      "blocked_profile_required",
    ],
  },
  {
    id: "other",
    title: "Прочее",
    ids: ["shared_folder", "unknown"],
  },
];

/**
 * Состояния синхронизации для галереи: каждое показано целиком (кнопка, строка
 * состояния, бейдж, панель в заголовке и на странице «Версии») из готовых данных.
 * Функция, а не константа: в обычную сборку галерея не попадает.
 */
export const getSyncGallery = (): GalleryGroup[] =>
  GROUPS.map((group) => ({
    id: group.id,
    title: group.title,
    entries: group.ids.flatMap((id) => {
      const fixture = SYNC_STATE_FIXTURES.find((item) => item.id === id);
      if (!fixture) return [];
      return [
        {
          id: fixture.id,
          title: fixture.title,
          note: fixture.note,
          frame: "plain" as const,
          render: () => <SyncStateSheet fixture={fixture} />,
        },
      ];
    }),
  }));
