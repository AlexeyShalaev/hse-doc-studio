import { useTranslation } from "react-i18next";
import { ErrorState } from "@shared/ui";

/** Словарь раздела не загрузился: сообщение берётся из основного бандла. */
export const LocalesFailed = ({ onRetry }: { onRetry: () => void }) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <ErrorState
      framed
      title={t("chunkError.title")}
      description={t("chunkError.text")}
      testId="admin-settings-locales-failed"
      onRetry={onRetry}
    />
  );
};
