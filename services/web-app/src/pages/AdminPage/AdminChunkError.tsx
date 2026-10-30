import { useTranslation } from "react-i18next";
import { Button, ResultFrame } from "@shared/ui";

/** Не загрузились словари или чанк админки: сообщение из основного бандла и повтор. */
export const AdminChunkError = ({ onRetry }: { onRetry: () => void }) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <div
      className="flex flex-1 items-center justify-center"
      style={{ padding: 24 }}
    >
      <div style={{ width: "100%", maxWidth: 480 }}>
        <ResultFrame
          tone="err"
          role="alert"
          testId="admin-chunk-error"
          title={t("chunkError.title")}
          actions={
            <Button
              size="sm"
              variant="ghost"
              type="button"
              data-testid="admin-chunk-retry"
              onClick={onRetry}
            >
              {t("dataTable.retry")}
            </Button>
          }
        >
          {t("chunkError.text")}
        </ResultFrame>
      </div>
    </div>
  );
};
