import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import {
  useFetchCloudBuild,
  type FetchBuildResponse,
  type FetchStatus,
} from "@entities/project-build";

const OK: ReadonlySet<FetchStatus> = new Set<FetchStatus>([
  "downloaded",
  "unchanged",
]);

const CODE = /^[a-z][a-z0-9_]*$/;

/**
 * Текст итога по документу. У `failed` он зависит от кода причины: «нет связи» только у `git_server_unreachable`
 * и сетевого сбоя, свои тексты у отказа в праве, нового входа, испорченного файла, записи на диск. Код ошибки
 * синхронизации без своего текста берётся из `errors:code.*`, неизвестный код даёт общий текст без догадок о связи.
 */
export const fetchResultText = (
  t: TFunction,
  status: FetchStatus,
  code: string | null,
): string => {
  if (status !== "failed") return t(`builds.result.${status}`);
  if (code === null || !CODE.test(code)) return t("builds.result.failed");
  return t([
    `builds.failure.${code}`,
    `errors:code.${code}`,
    "builds.result.failed",
  ]);
};

/** Код причины, когда запрос получения не прошёл целиком: сеть, отказ сервера Студии, проект не связан. */
export const fetchErrorCode = (error: unknown): string | null => {
  if (!(error instanceof ApiError)) return null;
  if (error.status === 0) return "network";
  if (error.code !== "unknown_error") return error.code;
  // Маршрут получения кладёт код сервера Студии в `detail` (`git_server_unreachable`, `auth_failed`).
  return CODE.test(error.detail) ? error.detail : null;
};

/** «Получить сборку»: запрос и понятный тост по итогу каждого документа. `force` заменяет и более свежую локальную. */
export const useFetchBuild = (projectId: string) => {
  const { t } = useTranslation("devices");
  const fetchBuild = useFetchCloudBuild(projectId);
  const report = (result: FetchBuildResponse): void => {
    for (const item of result.items) {
      const text = fetchResultText(t, item.status, item.code);
      if (OK.has(item.status)) toast.success(text);
      else toast.error(text);
    }
  };
  return {
    isPending: fetchBuild.isPending,
    run: (docId: string | null, force = false): void => {
      fetchBuild.mutate(
        { doc_id: docId, force, auto: false },
        {
          onSuccess: report,
          onError: (error) => {
            toast.error(fetchResultText(t, "failed", fetchErrorCode(error)));
          },
        },
      );
    },
  };
};
