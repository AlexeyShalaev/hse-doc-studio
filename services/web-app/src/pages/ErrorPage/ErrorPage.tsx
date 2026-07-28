import { AlertTriangle, ArrowLeft, Home, RotateCcw } from "lucide-react";
import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router";
import { useTranslation } from "react-i18next";
import { i18n } from "@shared/lib";

type ErrorPageProps = {
  status?: number;
  message?: string;
};

type ErrorMeta = {
  status: number;
  title: string;
  message: string;
  detail?: string;
};

const statusCopy = (status: number): Pick<ErrorMeta, "title" | "message"> => {
  if (status === 404) {
    return {
      title: i18n.t("errorPage.notFoundTitle", { ns: "appChrome" }),
      message: i18n.t("errorPage.notFoundMessage", { ns: "appChrome" }),
    };
  }
  if (status === 403) {
    return {
      title: i18n.t("errorPage.forbiddenTitle", { ns: "appChrome" }),
      message: i18n.t("errorPage.forbiddenMessage", { ns: "appChrome" }),
    };
  }
  if (status >= 500) {
    return {
      title: i18n.t("errorPage.serverTitle", { ns: "appChrome" }),
      message: i18n.t("errorPage.serverMessage", { ns: "appChrome" }),
    };
  }
  return {
    title: i18n.t("errorPage.genericTitle", { ns: "appChrome" }),
    message: i18n.t("errorPage.genericMessage", { ns: "appChrome" }),
  };
};

const getErrorMeta = (
  error: unknown,
  fallbackStatus: number,
  fallbackMessage?: string,
): ErrorMeta => {
  if (isRouteErrorResponse(error)) {
    const copy = statusCopy(error.status);
    const meta: ErrorMeta = {
      status: error.status,
      title: copy.title,
      message: fallbackMessage ?? copy.message,
    };
    if (error.statusText) meta.detail = error.statusText;
    return meta;
  }

  if (error instanceof Error) {
    const copy = statusCopy(fallbackStatus);
    return {
      status: fallbackStatus,
      title: copy.title,
      message: fallbackMessage ?? copy.message,
      detail: error.message,
    };
  }

  const copy = statusCopy(fallbackStatus);
  return {
    status: fallbackStatus,
    title: copy.title,
    message: fallbackMessage ?? copy.message,
  };
};

export const ErrorPage = ({ status = 500, message }: ErrorPageProps) => {
  const { t } = useTranslation("appChrome");
  const routeError = useRouteError();
  const navigate = useNavigate();
  const meta = getErrorMeta(routeError, status, message);

  return (
    <div
      className="flex flex-col h-screen bg-bg-0"
      style={{ color: "var(--fg-0)" }}
    >
      <div
        className="flex items-center"
        style={{
          height: 40,
          flexShrink: 0,
          gap: 8,
          padding: "0 12px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <AlertTriangle size={15} style={{ color: "var(--c-warn)" }} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>HSE Studio</span>
        <span className="mono dim" style={{ fontSize: 10 }}>
          ERROR {meta.status}
        </span>
      </div>

      <main
        className="flex flex-1 items-center justify-center"
        style={{ padding: 24 }}
      >
        <section
          className="flex flex-col"
          style={{
            width: "min(520px, 100%)",
            gap: 14,
            padding: 18,
            border: "1px solid var(--border)",
            borderRadius: "var(--r-3)",
            background: "var(--bg-1)",
            boxShadow: "var(--shadow-1)",
          }}
        >
          <div className="flex items-start" style={{ gap: 12 }}>
            <div
              className="flex items-center justify-center"
              style={{
                width: 34,
                height: 34,
                flexShrink: 0,
                borderRadius: "var(--r-2)",
                background: "var(--c-warn-soft)",
                color: "var(--c-warn)",
              }}
            >
              <AlertTriangle size={18} />
            </div>
            <div className="flex flex-col" style={{ gap: 5, minWidth: 0 }}>
              <div className="mono dim" style={{ fontSize: 10 }}>
                {meta.status}
              </div>
              <h1 style={{ margin: 0, fontSize: 20, lineHeight: 1.2 }}>
                {meta.title}
              </h1>
              <p
                className="dim"
                style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}
              >
                {meta.message}
              </p>
            </div>
          </div>

          {meta.detail && (
            <div
              className="mono"
              style={{
                padding: "9px 10px",
                borderRadius: "var(--r-2)",
                border: "1px solid var(--border)",
                background: "var(--bg-0)",
                color: "var(--fg-2)",
                fontSize: 11,
                lineHeight: 1.5,
                overflowWrap: "anywhere",
              }}
            >
              {meta.detail}
            </div>
          )}

          <div
            className="flex items-center"
            style={{ gap: 8, flexWrap: "wrap" }}
          >
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void navigate(-1);
              }}
            >
              <ArrowLeft size={11} />
              {t("errorPage.back")}
            </button>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void navigate("/", { replace: true });
              }}
            >
              <Home size={11} />
              {t("errorPage.home")}
            </button>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                window.location.reload();
              }}
            >
              <RotateCcw size={11} />
              {t("errorPage.reload")}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
};
