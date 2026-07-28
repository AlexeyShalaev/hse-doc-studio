import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import { useInvalidateImages } from "@entities/compile-images";

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
  const { t } = useTranslation("errors");

  return (err: unknown): boolean => {
    if (!(err instanceof ApiError) || err.status !== 409) return false;

    const goToImages = {
      label: t("common:actions.openSettings"),
      onClick: () => {
        void navigate("/settings/compiler");
      },
    };

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
