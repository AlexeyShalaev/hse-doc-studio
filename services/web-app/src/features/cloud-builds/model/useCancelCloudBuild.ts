import axios from "axios";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { useBootstrap } from "@entities/session";
import { useCancelCloudBuilds, useLocalBuilds } from "@entities/project-build";

/** Ключ текста в workbench:panel по ответу сервера: нет права, нужен новый вход, старый сервер, нет сети. */
export const cancelErrorKey = (error: unknown): string => {
  if (!axios.isAxiosError(error)) return "cancelFailed";
  const status = error.response?.status;
  if (status === 403) return "cancelForbidden";
  if (status === 401) return "cancelSignIn";
  if (status === 501) return "cancelUnsupported";
  if (status === undefined || status === 502) return "cancelOffline";
  return "cancelFailed";
};

/**
 * Локальная Студия: идёт ли у проекта сборка в облаке (по статусу сервера) и кнопка «Остановить облачную сборку».
 * Отмена идёт по входу Студии на сервер; итог (остановлено, уже закончилась, нет права, нет связи) показываем тостом.
 */
export const useCloudBuildStop = (projectId: string) => {
  const { t } = useTranslation("workbench");
  const isLocal = useBootstrap().data?.mode === "local";
  const builds = useLocalBuilds(projectId, isLocal);
  const cancel = useCancelCloudBuilds(projectId);
  const isCloudRunning =
    isLocal &&
    builds.data?.connected === true &&
    builds.data.documents.some((doc) => doc.cloud_running);
  return {
    isCloudRunning,
    isStopping: cancel.isPending,
    stop: (): void => {
      cancel.mutate(null, {
        onSuccess: (result) => {
          toast.success(
            t(
              result.cancelled > 0 ? "panel.cancelDone" : "panel.cancelNothing",
            ),
          );
        },
        onError: (error) => {
          toast.error(t(`panel.${cancelErrorKey(error)}`));
        },
      });
    },
  };
};
