import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import { useInvalidateImages } from "@entities/compile-images";
import { runnerKeys } from "@entities/runner";
import { useCapabilities } from "@entities/session";

/** Отказ сервера: для сборки сейчас нет раннера (гонка с опросом доступности). */
export const NO_RUNNER_CODES: ReadonlySet<string> = new Set([
  "no_runners",
  "no_runner_for_tags",
]);

/**
 * Centralised handler for compile-trigger errors. The axios interceptor
 * already suppresses auto-toast for 409, so this is where we turn the
 * structured `code` / `image` payload into a focused toast with a deep
 * link into Settings → Образы.
 *
 * Returns true if it handled the error (showed UI), so callers can skip
 * any generic fallback they had.
 */
export const useHandleCompileError = () => {
  const navigate = useNavigate();
  const invalidateImages = useInvalidateImages();
  const queryClient = useQueryClient();
  const { has } = useCapabilities();
  const { t } = useTranslation("errors");

  return (err: unknown): boolean => {
    if (!(err instanceof ApiError) || err.status !== 409) return false;

    const goToImages = {
      label: t("common:actions.openSettings"),
      onClick: () => {
        void navigate("/settings/compiler");
      },
    };

    if (NO_RUNNER_CODES.has(err.code)) {
      // Опрос доступности отстал от жизни: перечитываем, и кнопки погаснут сами.
      void queryClient.invalidateQueries({
        queryKey: [...runnerKeys.all, "availability"],
      });
      toast.error(t(`code.${err.code}`), {
        key: "compile-no-runners",
        title: t("compile.noRunnersTitle"),
        duration: 10_000,
        ...(has("admin")
          ? {
              action: {
                label: t("compile.openRunners"),
                onClick: () => {
                  void navigate("/admin/runners");
                },
              },
            }
          : {}),
      });
      return true;
    }

    if (err.code === "image_missing") {
      const image = typeof err.data?.image === "string" ? err.data.image : null;
      toast.error(image ? t("compile.imageMissing", { image }) : err.detail, {
        title: t("compile.imageMissingTitle"),
        duration: 10_000,
        action: goToImages,
      });
      invalidateImages();
      return true;
    }

    if (err.code === "docker_unavailable") {
      toast.error(err.detail, {
        title: t("compile.dockerUnavailableTitle"),
        duration: 10_000,
        action: goToImages,
      });
      invalidateImages();
      return true;
    }

    toast.error(err.detail, { title: t("compile.notStartedTitle") });
    return true;
  };
};
