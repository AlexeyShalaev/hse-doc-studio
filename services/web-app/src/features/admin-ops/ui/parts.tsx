import type { ReactNode } from "react";
import { CircleAlert, Info, Lock, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  EmptyState,
  ErrorState,
  PageTabs,
  TableSkeleton,
  type PageTab,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { failureKey, type Failure } from "../lib/failure";
import type { ViewStatus } from "../lib/viewStatus";
import "./ops.css";

/** Отказ из каталога ошибок. */
export const FailureNotice = ({ failure }: { failure: Failure }) => {
  const { t } = useTranslation("adminOps");
  return (
    <div data-testid="ops-failure">
      <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
    </div>
  );
};

export type BannerTone = "danger" | "warning" | "info";

const BANNER_ICON: Record<BannerTone, ReactNode> = {
  danger: <CircleAlert size={16} aria-hidden="true" />,
  warning: <TriangleAlert size={16} aria-hidden="true" />,
  info: <Info size={16} aria-hidden="true" />,
};

/** Заметная строка над содержимым: что сломано и что из этого следует. */
export const Banner = ({
  tone,
  title,
  children,
  action,
  testId,
}: {
  tone: BannerTone;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  testId?: string;
}) => (
  <div
    className="ops-banner"
    data-tone={tone}
    role={tone === "info" ? "status" : "alert"}
    data-testid={testId}
  >
    <span className="ops-banner-icon">{BANNER_ICON[tone]}</span>
    <div className="ops-banner-text">
      <p className="ops-banner-title">{title}</p>
      {children && <p className="ops-banner-body">{children}</p>}
    </div>
    {action && <div className="ops-banner-action">{action}</div>}
  </div>
);

/**
 * Вид, пока данных нет: скелет, ошибка с повтором или нет прав.
 * Когда данные готовы, ничего не рисует.
 */
export const ViewState = ({
  status,
  errorText,
  onRetry,
  skeleton,
  compact = false,
  testId,
}: {
  status: ViewStatus;
  errorText: string;
  onRetry?: (() => void) | undefined;
  /** Что показать при загрузке; по умолчанию скелет таблицы. */
  skeleton?: ReactNode;
  /** Одна строка: для блока внутри карточки. */
  compact?: boolean;
  testId?: string;
}) => {
  const { t } = useTranslation("adminOps");
  if (status === "loading") {
    return (
      <div data-testid={testId ? `${testId}-loading` : undefined}>
        {skeleton ?? <TableSkeleton rows={4} columns={4} />}
      </div>
    );
  }
  if (status === "forbidden") {
    return (
      <EmptyState
        framed={!compact}
        compact={compact}
        icon={<Lock size={compact ? 15 : 18} />}
        title={t("forbidden.title")}
        description={t("forbidden.body")}
        testId={testId ? `${testId}-forbidden` : "ops-forbidden"}
      />
    );
  }
  if (status === "error") {
    return (
      <ErrorState
        framed={!compact}
        compact={compact}
        description={errorText}
        onRetry={onRetry}
        testId={testId ? `${testId}-error` : undefined}
      />
    );
  }
  return null;
};

/** Вкладки раздела: общие вкладки админки с testid ops-tab-<id>. */
export const Tabs = <T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: readonly PageTab<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
}) => (
  <PageTabs
    label={label}
    value={value}
    onChange={onChange}
    idPrefix="ops-tab"
    panelId="ops-tab-panel"
    tabs={tabs.map((tab) => ({ ...tab, testId: `ops-tab-${tab.id}` }))}
  />
);
