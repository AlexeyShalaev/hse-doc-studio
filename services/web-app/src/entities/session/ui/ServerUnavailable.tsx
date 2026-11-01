import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";

export type ServerUnavailableProps = {
  onRetry: () => void;
  retrying?: boolean;
};

/**
 * Сервер не ответил на bootstrap. Без него неизвестно, кто пользователь и что
 * ему можно, поэтому вместо приложения стоит это сообщение с повтором.
 */
export const ServerUnavailable = ({
  onRetry,
  retrying = false,
}: ServerUnavailableProps) => {
  const { t } = useTranslation("session");
  return (
    <div
      data-testid="server-unavailable"
      style={{
        minHeight: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div style={{ width: "100%", maxWidth: 460 }}>
        <ResultFrame
          tone="err"
          role="alert"
          testId="server-unavailable-frame"
          title={t("unavailable.title")}
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={onRetry}
              disabled={retrying}
              data-testid="server-unavailable-retry"
            >
              <RotateCcw size={14} aria-hidden />
              {t("unavailable.retry")}
            </Button>
          }
        >
          {t("unavailable.body")}
        </ResultFrame>
      </div>
    </div>
  );
};
