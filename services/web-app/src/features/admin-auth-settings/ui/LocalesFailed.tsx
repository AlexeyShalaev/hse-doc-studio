import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

/** Словарь раздела не загрузился: сообщение берётся из основного бандла. */
export const LocalesFailed = ({ onRetry }: { onRetry: () => void }) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <Notice
      tone="err"
      role="alert"
      text={t("chunkError.title")}
      action={
        <Button
          size="sm"
          variant="ghost"
          type="button"
          data-testid="admin-settings-locales-retry"
          onClick={onRetry}
        >
          {t("dataTable.retry")}
        </Button>
      }
    />
  );
};
