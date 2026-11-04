import { CloudOff, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui/Spinner";

export type LoadErrorProps = {
  onRetry: () => void;
  retrying?: boolean;
};

/** Список проектов не загрузился: отдельное состояние, а не «проектов нет». */
export const LoadError = ({ onRetry, retrying = false }: LoadErrorProps) => {
  const { t } = useTranslation("projectAccess");
  return (
    <div
      className="card"
      role="alert"
      style={{ padding: "3rem 2rem", textAlign: "center" }}
    >
      <div
        className="flex items-center justify-center"
        style={{
          width: "4rem",
          height: "4rem",
          margin: "0 auto 1.125rem",
          borderRadius: "1rem",
          background: "var(--c-warn-soft)",
          border: "1px solid var(--border)",
          color: "var(--c-warn)",
        }}
      >
        <CloudOff size="1.875rem" aria-hidden="true" />
      </div>
      <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
        {t("loadError.title")}
      </h3>
      <p
        className="dim"
        style={{
          margin: "0.5rem auto 1.125rem",
          maxWidth: "26.25rem",
          lineHeight: 1.5,
        }}
      >
        {t("loadError.description")}
      </p>
      <button
        type="button"
        className="btn primary"
        onClick={onRetry}
        disabled={retrying}
      >
        {retrying ? <Spinner size="sm" /> : <RotateCcw size="0.8125rem" />}
        {t("loadError.retry")}
      </button>
    </div>
  );
};
