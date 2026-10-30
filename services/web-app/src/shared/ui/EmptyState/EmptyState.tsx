import type { ReactNode } from "react";
import { CircleAlert, Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";

// Пустое состояние и ошибка загрузки: значок, заголовок, одна фраза, действие.
// compact: в одну строку, для блоков внутри карточек.

export type EmptyStateProps = {
  title: ReactNode;
  description?: ReactNode | undefined;
  icon?: ReactNode | undefined;
  /** Главное действие: обычно кнопка primary. */
  action?: ReactNode | undefined;
  compact?: boolean | undefined;
  /** Пунктирная рамка: когда блок стоит сам по себе, не в карточке. */
  framed?: boolean | undefined;
  testId?: string | undefined;
};

export const EmptyState = ({
  title,
  description,
  icon,
  action,
  compact = false,
  framed = false,
  testId,
}: EmptyStateProps) => (
  <div
    className="adm-state"
    data-compact={compact ? "true" : undefined}
    data-framed={framed ? "true" : undefined}
    data-testid={testId}
  >
    <span className="adm-state-icon" aria-hidden="true">
      {icon ?? <Inbox size={compact ? 15 : 18} />}
    </span>
    <div className="adm-state-text">
      <p className="adm-state-title">{title}</p>
      {description && <p className="adm-state-desc">{description}</p>}
    </div>
    {action && <div className="adm-state-action">{action}</div>}
  </div>
);

export type ErrorStateProps = {
  /** По умолчанию «Не удалось загрузить данные». */
  title?: ReactNode | undefined;
  description?: ReactNode | undefined;
  onRetry?: (() => void) | undefined;
  /** Повтор уже идёт. */
  retrying?: boolean | undefined;
  compact?: boolean | undefined;
  framed?: boolean | undefined;
  testId?: string | undefined;
};

export const ErrorState = ({
  title,
  description,
  onRetry,
  retrying = false,
  compact = false,
  framed = false,
  testId,
}: ErrorStateProps) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <div
      className="adm-state"
      role="alert"
      data-tone="danger"
      data-compact={compact ? "true" : undefined}
      data-framed={framed ? "true" : undefined}
      data-testid={testId}
    >
      <span className="adm-state-icon" aria-hidden="true">
        <CircleAlert size={compact ? 15 : 18} />
      </span>
      <div className="adm-state-text">
        <p className="adm-state-title">{title ?? t("adminKit.error.title")}</p>
        {description && <p className="adm-state-desc">{description}</p>}
      </div>
      {onRetry && (
        <div className="adm-state-action">
          <button
            type="button"
            className="btn sm"
            disabled={retrying}
            onClick={onRetry}
          >
            {t("adminKit.error.retry")}
          </button>
        </div>
      )}
    </div>
  );
};

EmptyState.displayName = "EmptyState";
ErrorState.displayName = "ErrorState";
