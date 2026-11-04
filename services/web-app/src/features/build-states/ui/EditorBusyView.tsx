import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, FileEdit, RefreshCw, Users } from "lucide-react";

export type EditorBusyViewProps = {
  /** Через сколько секунд сервер советует повторить. */
  retryAfterSeconds: number;
  /** Сколько одновременных сессий редактора допускает установка. */
  limit: number;
  onRetry: () => void;
  /** Адрес файла документа: запасной путь, пока редактор занят. */
  downloadHref: string | null;
  downloadName?: string;
};

/**
 * Редактор документов занят: лимит одновременных сессий исчерпан. Показываем,
 * когда пробовать снова (с обратным отсчётом), и даём скачать файл, чтобы
 * не терять время.
 */
export const EditorBusyView = ({
  retryAfterSeconds,
  limit,
  onRetry,
  downloadHref,
  downloadName,
}: EditorBusyViewProps) => {
  const { t } = useTranslation("documents");
  const [elapsed, setElapsed] = useState(0);
  const left = Math.max(0, retryAfterSeconds - elapsed);

  useEffect(() => {
    const id = window.setInterval(() => {
      setElapsed((n) => n + 1);
    }, 1000);
    return () => {
      window.clearInterval(id);
    };
  }, []);

  return (
    <div
      data-testid="editor-busy"
      className="flex flex-col items-center justify-center"
      style={{
        flex: 1,
        padding: "2.5rem",
        gap: "1rem",
        minHeight: 0,
        overflowY: "auto",
      }}
    >
      <div
        className="stripes flex items-center justify-center"
        style={{
          width: "15rem",
          height: "8.4375rem",
          borderRadius: "0.375rem",
          border: "1px solid var(--border-strong)",
          color: "var(--fg-3)",
          position: "relative",
        }}
      >
        <FileEdit size="1.75rem" />
        <Users
          size="1rem"
          style={{
            position: "absolute",
            right: "0.75rem",
            bottom: "0.625rem",
            color: "var(--c-warn)",
          }}
        />
      </div>
      <span style={{ fontSize: "0.875rem", fontWeight: 600 }}>
        {t("office.busy.title")}
      </span>
      <p
        className="dim"
        style={{
          margin: 0,
          textAlign: "center",
          maxWidth: "27.5rem",
          fontSize: "0.78125rem",
          lineHeight: 1.5,
        }}
      >
        {t("office.busy.body", { limit })}
      </p>
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn primary"
          onClick={onRetry}
          disabled={left > 0}
        >
          <RefreshCw size="0.75rem" />
          {left > 0
            ? t("office.busy.retryIn", { seconds: left })
            : t("office.busy.retry")}
        </button>
        {downloadHref && (
          <a
            href={downloadHref}
            download={downloadName ?? true}
            className="btn"
          >
            <Download size="0.75rem" />
            {t("office.busy.download")}
          </a>
        )}
      </div>
      <span
        className="dim"
        style={{ fontSize: "0.6875rem", maxWidth: "27.5rem" }}
      >
        {t("office.busy.downloadHint")}
      </span>
    </div>
  );
};
