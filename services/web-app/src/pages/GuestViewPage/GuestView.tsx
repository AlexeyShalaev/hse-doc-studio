import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Eye, FileText } from "lucide-react";
import { Link } from "react-router";
import { Badge, EmptyState, ErrorState, Spinner } from "@shared/ui";

export type GuestViewDoc = {
  id: string;
  name: string;
  /** Адрес последнего удачного PDF; null, если документ ещё не собран. */
  pdfUrl: string | null;
  pages: number | null;
};

export type GuestViewProps = {
  projectName: string;
  status: "loading" | "error" | "ready";
  docs: readonly GuestViewDoc[];
  onRetry?: () => void;
  /** Галерея показывает встроенный просмотр без настоящего PDF. */
  embed?: boolean;
};

/** Читатель без исходников (10.4): документы и последний PDF каждого с просмотром и скачиванием. */
export const GuestView = ({
  projectName,
  status,
  docs,
  onRetry,
  embed = true,
}: GuestViewProps) => {
  const { t } = useTranslation("guest");
  const firstBuilt = docs.find((doc) => doc.pdfUrl !== null)?.id ?? null;
  const [selected, setSelected] = useState<string | null>(null);
  const current =
    docs.find((doc) => doc.id === (selected ?? firstBuilt)) ?? null;

  return (
    <div
      className="flex flex-col"
      style={{
        gap: 16,
        padding: "24px",
        width: "100%",
        maxWidth: 1100,
        margin: "0 auto",
      }}
      data-testid="guest-view"
    >
      <div>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {projectName}
        </h1>
        <p style={{ margin: "6px 0 0", color: "var(--fg-2)", fontSize: 13 }}>
          {t("view.lead")}
        </p>
      </div>
      {status === "loading" && <Spinner />}
      {status === "error" && (
        <ErrorState
          framed
          title={t("view.loadFailed")}
          {...(onRetry ? { onRetry } : {})}
        />
      )}
      {status === "ready" && docs.length === 0 && (
        <EmptyState framed title={t("view.empty")} />
      )}
      {status === "ready" && docs.length > 0 && (
        <div
          className="flex"
          style={{ gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}
        >
          <ul
            className="flex flex-col"
            style={{
              gap: 8,
              listStyle: "none",
              margin: 0,
              padding: 0,
              flex: "0 0 320px",
              minWidth: 0,
            }}
          >
            {docs.map((doc) => (
              <li
                key={doc.id}
                data-testid={`guest-view-doc-${doc.id}`}
                className="flex items-center"
                style={{
                  gap: 10,
                  padding: 12,
                  borderRadius: "var(--r-3)",
                  border: `1px solid ${current?.id === doc.id ? "var(--accent-line, var(--border))" : "var(--border)"}`,
                  background: "var(--bg-1)",
                }}
              >
                <FileText
                  size={16}
                  aria-hidden="true"
                  style={{ color: "var(--fg-2)", flexShrink: 0 }}
                />
                <div
                  className="flex flex-col"
                  style={{ flex: 1, minWidth: 0, gap: 2 }}
                >
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {doc.name}
                  </span>
                  {doc.pdfUrl === null ? (
                    <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
                      {t("view.notBuilt")}
                    </span>
                  ) : (
                    doc.pages !== null && (
                      <Badge variant="subtle">PDF · {doc.pages}</Badge>
                    )
                  )}
                </div>
                {doc.pdfUrl !== null && (
                  <>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={t("view.preview")}
                      onClick={() => {
                        setSelected(doc.id);
                      }}
                    >
                      <Eye size={15} />
                    </button>
                    <a
                      className="icon-btn"
                      href={doc.pdfUrl}
                      download={`${doc.name}.pdf`}
                      aria-label={t("view.download")}
                      data-testid={`guest-view-download-${doc.id}`}
                    >
                      <Download size={15} />
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
          {current?.pdfUrl && (
            <div
              style={{
                flex: "1 1 480px",
                minWidth: 0,
                height: "75vh",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-3)",
                overflow: "hidden",
                background: "var(--bg-2)",
              }}
            >
              {embed ? (
                <iframe
                  title={current.name}
                  src={current.pdfUrl}
                  style={{ width: "100%", height: "100%", border: 0 }}
                />
              ) : (
                <div
                  className="flex items-center justify-center"
                  style={{ height: "100%", color: "var(--fg-2)", fontSize: 13 }}
                >
                  PDF · {current.name}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      <div>
        <Link to="/" className="btn ghost sm">
          {t("view.back")}
        </Link>
      </div>
    </div>
  );
};
