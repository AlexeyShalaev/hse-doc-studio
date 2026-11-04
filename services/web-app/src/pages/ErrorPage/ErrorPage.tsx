import { AlertTriangle, ArrowLeft, Bug, Home, RotateCcw } from "lucide-react";
import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router";
import { useTranslation } from "react-i18next";
import { i18n } from "@shared/lib";

const REPO_URL = "https://github.com/AlexeyShalaev/hse-doc-studio";
// GitHub обрезает слишком длинные prefill-URL — стек ограничиваем заранее.
const STACK_LIMIT = 1600;

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

// Готовая issue на GitHub: заголовок и тело с ошибкой, стеком и окружением уже
// заполнены — пользователю остаётся дописать, что он делал, и нажать Submit.
const buildIssueUrl = (meta: ErrorMeta, error: unknown): string => {
  const stack =
    error instanceof Error && error.stack
      ? error.stack.slice(0, STACK_LIMIT)
      : "";
  const title = `[bug] ${meta.status}: ${(meta.detail ?? meta.title).slice(0, 120)}`;
  const body = [
    "**What happened**",
    "",
    "<!-- Что вы делали, когда возникла ошибка? / What were you doing when it broke? -->",
    "",
    "**Error**",
    "```",
    `${meta.status}: ${meta.detail ?? meta.title}`,
    ...(stack ? ["", stack] : []),
    "```",
    "",
    "**Environment**",
    "",
    `- Route: \`${window.location.pathname}\``,
    `- App: ${__APP_VERSION__}`,
    `- Browser: ${navigator.userAgent}`,
  ].join("\n");
  const params = new URLSearchParams({ title, body, labels: "bug" });
  return `${REPO_URL}/issues/new?${params.toString()}`;
};

export const ErrorPage = ({ status = 500, message }: ErrorPageProps) => {
  const { t } = useTranslation("appChrome");
  const routeError = useRouteError();
  const navigate = useNavigate();
  const meta = getErrorMeta(routeError, status, message);

  return (
    <div
      className="flex flex-col h-dvh bg-bg-0"
      style={{ color: "var(--fg-0)" }}
    >
      <div
        className="flex items-center"
        style={{
          height: "2.5rem",
          flexShrink: 0,
          gap: "0.5rem",
          padding: "0 0.75rem",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <AlertTriangle size="0.9375rem" style={{ color: "var(--c-warn)" }} />
        <span style={{ fontSize: "0.8125rem", fontWeight: 600 }}>
          HSE Studio
        </span>
        <span className="mono dim" style={{ fontSize: "0.625rem" }}>
          ERROR {meta.status}
        </span>
      </div>

      <main
        className="flex flex-1 items-center justify-center"
        style={{ padding: "1.5rem" }}
      >
        <section
          className="flex flex-col"
          style={{
            width: "min(32.5rem, 100%)",
            gap: "0.875rem",
            padding: "1.125rem",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-3)",
            background: "var(--bg-1)",
            boxShadow: "var(--shadow-1)",
          }}
        >
          <div className="flex items-start" style={{ gap: "0.75rem" }}>
            <div
              className="flex items-center justify-center"
              style={{
                width: "2.125rem",
                height: "2.125rem",
                flexShrink: 0,
                borderRadius: "var(--r-2)",
                background: "var(--c-warn-soft)",
                color: "var(--c-warn)",
              }}
            >
              <AlertTriangle size="1.125rem" />
            </div>
            <div
              className="flex flex-col"
              style={{ gap: "0.3125rem", minWidth: 0 }}
            >
              <div className="mono dim" style={{ fontSize: "0.625rem" }}>
                {meta.status}
              </div>
              <h1 style={{ margin: 0, fontSize: "1.25rem", lineHeight: 1.2 }}>
                {meta.title}
              </h1>
              <p
                className="dim"
                style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
              >
                {meta.message}
              </p>
            </div>
          </div>

          {meta.detail && (
            <div
              className="mono"
              style={{
                padding: "0.5625rem 0.625rem",
                borderRadius: "var(--r-2)",
                border: "1px solid var(--border)",
                background: "var(--bg-0)",
                color: "var(--fg-2)",
                fontSize: "0.6875rem",
                lineHeight: 1.5,
                overflowWrap: "anywhere",
              }}
            >
              {meta.detail}
            </div>
          )}

          <div
            className="flex items-center"
            style={{ gap: "0.5rem", flexWrap: "wrap" }}
          >
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void navigate(-1);
              }}
            >
              <ArrowLeft size="0.6875rem" />
              {t("errorPage.back")}
            </button>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void navigate("/", { replace: true });
              }}
            >
              <Home size="0.6875rem" />
              {t("errorPage.home")}
            </button>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                window.location.reload();
              }}
            >
              <RotateCcw size="0.6875rem" />
              {t("errorPage.reload")}
            </button>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                window.open(
                  buildIssueUrl(meta, routeError),
                  "_blank",
                  "noopener",
                );
              }}
            >
              <Bug size="0.6875rem" />
              {t("errorPage.report")}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
};
