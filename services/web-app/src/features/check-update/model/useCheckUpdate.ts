import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  systemApi,
  systemKeys,
  useReleaseNotes,
  useSystemInfo,
  type CheckUpdatesResponse,
  type ReleaseEntry,
  type SystemInfo,
} from "@entities/system";
import { isCheckStale } from "../lib/isCheckStale";

export type CheckUpdateResult = {
  currentVersion: string | null;
  latestVersion: string | null;
  updateAvailable: boolean;
  releases: ReleaseEntry[];
  /** Заметки именно про доступную версию (в форке её может не быть в списке). */
  latestRelease: ReleaseEntry | null;
  deploymentMode: SystemInfo["deployment_mode"] | null;
  isChecking: boolean;
  /** Знаем ли мы результат проверки — хоть из кэша, хоть только что полученный. */
  hasInfo: boolean;
  /** Фид выключен (закрытый контур): проверять нечего, кнопку показывать не нужно. */
  feedEnabled: boolean;
  /** Почему последняя проверка не удалась; пусто, когда всё в порядке. */
  reason: string;
  check: () => void;
};

export const useCheckUpdate = (): CheckUpdateResult => {
  const queryClient = useQueryClient();
  const { data: info } = useSystemInfo();
  // Заметки — локальные данные сборки, к сети не ходят: «Что нового» открывается
  // и при выключенном фиде, и когда GitHub недоступен.
  const { data: notes } = useReleaseNotes(info !== undefined);

  const [reason, setReason] = useState("");

  const checkMutation = useMutation<CheckUpdatesResponse>({
    mutationFn: () => systemApi.checkUpdates(),
    onSuccess: (result) => {
      setReason(result.reason);
      // Единственный источник состояния обновлений — /system/info; после проверки
      // просто перечитываем его, а не держим вторую копию тех же полей. Заметки
      // о доступной версии лежат в том же кэше на бэкенде, поэтому «Что нового»
      // одинаково открывается и сразу после проверки, и в соседней вкладке.
      void queryClient.invalidateQueries({ queryKey: systemKeys.info() });
    },
    retry: false,
  });

  // Фоновая проверка при первом показе, если прошлая была давно. То же правило,
  // что и раньше, только отметка времени теперь на бэкенде.
  const autoCheckedRef = useRef(false);
  const { mutate } = checkMutation;
  useEffect(() => {
    if (autoCheckedRef.current || info === undefined) return;
    if (!info.update_feed_enabled || !isCheckStale(info.update_checked_at)) {
      return;
    }
    autoCheckedRef.current = true;
    mutate();
  }, [info, mutate]);

  const check = useCallback(() => {
    mutate();
  }, [mutate]);

  const releases = notes?.releases ?? [];
  // Бэкенд отдаёт "" вместо null, когда проверок ещё не было.
  const knownLatest = info?.latest_version ?? "";
  const latestVersion = knownLatest === "" ? null : knownLatest;
  // Курируемые заметки — если эта версия уже установлена (обычная история после
  // обновления); иначе то, что удалось узнать из фида при последней проверке.
  const feedNotes = info?.latest_release_notes ?? [];
  const latestRelease: ReleaseEntry | null =
    releases.find((release) => release.version === latestVersion) ??
    (latestVersion !== null && feedNotes.length > 0
      ? {
          version: latestVersion,
          date: info?.latest_release_date ?? "",
          notes: feedNotes,
        }
      : null);

  return {
    currentVersion: info?.version ?? null,
    latestVersion,
    updateAvailable: info?.update_available ?? false,
    releases,
    latestRelease,
    deploymentMode: info?.deployment_mode ?? null,
    isChecking: checkMutation.isPending,
    hasInfo: info !== undefined && Boolean(info.update_checked_at),
    feedEnabled: info?.update_feed_enabled ?? false,
    reason,
    check,
  };
};
