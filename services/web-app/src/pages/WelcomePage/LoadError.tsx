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
      style={{ padding: "48px 32px", textAlign: "center" }}
    >
      <div
        className="flex items-center justify-center"
        style={{
          width: 64,
          height: 64,
          margin: "0 auto 18px",
          borderRadius: 16,
          background: "var(--c-warn-soft)",
          border: "1px solid var(--border)",
          color: "var(--c-warn)",
        }}
      >
        <CloudOff size={30} aria-hidden="true" />
      </div>
      <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
        {t("loadError.title")}
      </h3>
      <p
        className="dim"
        style={{ margin: "8px auto 18px", maxWidth: 420, lineHeight: 1.5 }}
      >
        {t("loadError.description")}
      </p>
      <button
        type="button"
        className="btn primary"
        onClick={onRetry}
        disabled={retrying}
      >
        {retrying ? <Spinner size="sm" /> : <RotateCcw size={13} />}
        {t("loadError.retry")}
      </button>
    </div>
  );
};
