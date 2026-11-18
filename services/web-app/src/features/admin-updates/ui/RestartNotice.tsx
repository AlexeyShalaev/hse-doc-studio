import { useEffect } from "react";
import { Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { formatDuration, type Executor } from "../lib/progress";
import { useNow } from "../model/useNow";
import "./updates.css";

/** Сколько минут обычно длится перезапуск при обновлении: образ до 10 минут, миграции и проверка здоровья. */
export const EXPECTED_RESTART_MIN = 15;

export type RestartNoticeProps = {
  /** Когда простой замечен (мс). */
  since: number;
  attempts: number;
  /** Во время обновления перезапуск ожидаем, без него это просто «нет связи». */
  updating: boolean;
  executor: Executor;
  onRetryNow: () => void;
};

/**
 * Экран на время, пока api недоступен: не ошибка, а ожидание. Опрос идёт сам, здесь показано, сколько ждём и
 * сколько ждать нормально; кнопка проверяет немедленно.
 */
export const RestartNotice = ({
  since,
  attempts,
  updating,
  executor,
  onRetryNow,
}: RestartNoticeProps) => {
  const { t } = useTranslation("adminUpdates");
  const now = useNow(true);
  const waited = Math.max(0, Math.round((now - since) / 1000));
  const slow = waited > EXPECTED_RESTART_MIN * 60;
  const units = { h: t("units.h"), min: t("units.min"), s: t("units.s") };
  // Вкладка в фоне не должна считать простой «бесконечным»: возврат на неё сразу проверяет сервер.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") onRetryNow();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [onRetryNow]);
  return (
    <div
      className="upd-card"
      data-tone={slow ? "warn" : "info"}
      data-testid="update-restart"
    >
      <div className="upd-card-head">
        {slow ? (
          <TriangleAlert
            size="1.125rem"
            aria-hidden="true"
            className="upd-card-icon"
          />
        ) : (
          <Loader2
            size="1.125rem"
            aria-hidden="true"
            className="upd-card-icon upd-spin"
          />
        )}
        <div style={{ minWidth: 0 }}>
          <h3 className="upd-card-title">
            {t(updating ? "restart.title" : "restart.titleGeneric")}
          </h3>
          <p className="upd-card-sub" role="status" aria-live="polite">
            {updating
              ? t("restart.body", { minutes: EXPECTED_RESTART_MIN })
              : t("restart.bodyGeneric")}
          </p>
        </div>
      </div>
      <p className="upd-meta" data-testid="update-restart-wait">
        <span>
          {t("restart.waited", { time: formatDuration(waited, units) })}
        </span>
        <span>{t("restart.attempts", { count: attempts })}</span>
      </p>
      {slow && (
        <p className="upd-card-sub" data-testid="update-restart-slow">
          {t(
            executor === "kubernetes"
              ? "restart.slowKube"
              : "restart.slowCompose",
          )}
        </p>
      )}
      <div className="upd-actions">
        <Button
          size="sm"
          variant="ghost"
          data-testid="update-restart-retry"
          onClick={onRetryNow}
        >
          <RefreshCw size="0.875rem" />
          {t("restart.retry")}
        </Button>
      </div>
    </div>
  );
};
