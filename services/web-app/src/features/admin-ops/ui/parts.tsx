import type { CSSProperties, ReactNode } from "react";
import { Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { failureKey, type Failure } from "../lib/failure";
import { CARD } from "../lib/styles";

/** Отказ из каталога ошибок. */
export const FailureNotice = ({ failure }: { failure: Failure }) => {
  const { t } = useTranslation("adminOps");
  return (
    <div data-testid="ops-failure">
      <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
    </div>
  );
};

export const LoadingRow = ({ testId }: { testId?: string }) => {
  const { t } = useTranslation("adminOps");
  return (
    <div
      className="flex items-center"
      style={{ gap: 8, fontSize: 12 }}
      data-testid={testId ?? "ops-loading"}
      role="status"
    >
      <Spinner size="sm" />
      <span className="dim">{t("loading")}</span>
    </div>
  );
};

export const LoadFailed = ({
  text,
  onRetry,
}: {
  text: string;
  onRetry?: (() => void) | undefined;
}) => {
  const { t } = useTranslation("adminOps");
  return (
    <Notice
      tone="err"
      role="alert"
      text={text}
      action={
        onRetry && (
          <button type="button" className="btn xs" onClick={onRetry}>
            {t("retry")}
          </button>
        )
      }
    />
  );
};

/** Пустое состояние: значок, заголовок, пояснение и действие. */
export const EmptyBlock = ({
  icon,
  title,
  body,
  action,
  testId,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  testId?: string;
}) => (
  <div
    className="flex flex-col items-start"
    style={{
      gap: 8,
      padding: 20,
      border: "1px dashed var(--border)",
      borderRadius: "var(--r-2)",
    }}
    data-testid={testId}
  >
    <span style={{ color: "var(--fg-3)" }}>
      {icon ?? <Inbox size={18} aria-hidden="true" />}
    </span>
    <strong style={{ fontSize: 13 }}>{title}</strong>
    {body && (
      <span style={{ fontSize: 12, color: "var(--fg-2)", maxWidth: 480 }}>
        {body}
      </span>
    )}
    {action}
  </div>
);

/** Заголовок раздела. */
export const PageHeader = ({
  title,
  lead,
  action,
}: {
  title: string;
  lead: string;
  action?: ReactNode;
}) => (
  <div className="flex items-start" style={{ gap: 12 }}>
    <header className="flex flex-col" style={{ gap: 4, flex: 1 }}>
      <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>{title}</h1>
      <p style={{ margin: 0, fontSize: 13, color: "var(--fg-2)" }}>{lead}</p>
    </header>
    {action}
  </div>
);

/** Карточка со своим заголовком. */
export const Card = ({
  title,
  lead,
  action,
  children,
  testId,
  style,
}: {
  title: string;
  lead?: string;
  action?: ReactNode;
  children: ReactNode;
  testId?: string;
  style?: CSSProperties;
}) => (
  <section
    className="flex flex-col"
    style={{ ...CARD, gap: 12, padding: 16, ...style }}
    data-testid={testId}
  >
    <div className="flex items-start" style={{ gap: 12 }}>
      <div className="flex flex-col" style={{ gap: 2, flex: 1, minWidth: 0 }}>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h2>
        {lead && (
          <p style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}>
            {lead}
          </p>
        )}
      </div>
      {action}
    </div>
    {children}
  </section>
);

/** Цифра с подписью для сводок. */
export const Stat = ({
  label,
  value,
  hint,
  tone,
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "warn" | "err" | undefined;
  testId?: string;
}) => (
  <div
    className="flex flex-col"
    style={{ ...CARD, gap: 2, padding: "10px 14px", minWidth: 0 }}
    data-testid={testId}
  >
    <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>{label}</span>
    <span
      style={{
        fontSize: 20,
        fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
        color:
          tone === "err"
            ? "var(--c-err)"
            : tone === "warn"
              ? "var(--c-warn)"
              : "var(--fg-0)",
      }}
    >
      {value}
    </span>
    {hint && <span style={{ fontSize: 11, color: "var(--fg-3)" }}>{hint}</span>}
  </div>
);

export const StatRow = ({ children }: { children: ReactNode }) => (
  <div
    style={{
      display: "grid",
      gap: 10,
      gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    }}
  >
    {children}
  </div>
);

/** Горизонтальная полоса заполнения. */
export const Meter = ({
  value,
  label,
  tone = "accent",
}: {
  value: number;
  label: string;
  tone?: "accent" | "warn" | "err";
}) => (
  <div
    role="progressbar"
    aria-label={label}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={value}
    style={{
      height: 6,
      borderRadius: 3,
      background: "var(--bg-3)",
      overflow: "hidden",
      minWidth: 60,
    }}
  >
    <div
      style={{
        width: `${String(value)}%`,
        height: "100%",
        background:
          tone === "err"
            ? "var(--c-err)"
            : tone === "warn"
              ? "var(--c-warn)"
              : "var(--accent)",
      }}
    />
  </div>
);

/** Переключатель вкладок раздела. */
export const Tabs = <T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: readonly { id: T; label: string; count?: number }[];
  value: T;
  onChange: (id: T) => void;
  label: string;
}) => (
  <div
    role="tablist"
    aria-label={label}
    className="flex"
    style={{ gap: 4, borderBottom: "1px solid var(--border)" }}
  >
    {tabs.map((tab) => {
      const active = tab.id === value;
      return (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active}
          data-testid={`ops-tab-${tab.id}`}
          className="row-btn"
          onClick={() => {
            onChange(tab.id);
          }}
          style={{
            padding: "8px 12px",
            borderRadius: "var(--r-2) var(--r-2) 0 0",
            borderBottom: active
              ? "2px solid var(--accent)"
              : "2px solid transparent",
            fontWeight: active ? 600 : 400,
            gap: 6,
          }}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="chip subtle">{tab.count}</span>
          )}
        </button>
      );
    })}
  </div>
);
