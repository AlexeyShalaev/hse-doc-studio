import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

/** Загрузка карточки или отказ с повтором. */
export const LoadState = ({
  failed,
  onRetry,
}: {
  failed: boolean;
  onRetry: () => void;
}) => {
  const { t } = useTranslation("adminInstall");
  if (failed) {
    return (
      <Notice
        tone="err"
        role="alert"
        text={t("loadFailed")}
        action={
          <button type="button" className="btn xs" onClick={onRetry}>
            {t("retry")}
          </button>
        }
      />
    );
  }
  return (
    <div
      className="flex items-center"
      style={{ gap: 8, fontSize: 12 }}
      role="status"
      data-testid="install-loading"
    >
      <Spinner size="sm" />
      <span className="dim">{t("loading")}</span>
    </div>
  );
};
