import axios from "axios";
import { env } from "@shared/config";
import { toast, i18n, useThemeStore } from "@shared/lib";

declare module "axios" {
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  export interface AxiosRequestConfig {
    /**
     * Не показывать тост об ошибке — вызывающий разбирается сам.
     *
     * Нужно там, где отказ ЗАПЛАНИРОВАН и ошибкой не является. Ровно такой
     * случай — опрос состояния, пока приложение пересоздаёт собственный
     * контейнер: сервер в этот момент недоступен по нашей же воле, и каждый
     * неудавшийся запрос вылезал красным «Network Error» поверх экрана, где
     * честно написано «ждём, когда оно вернётся».
     */
    silentError?: boolean;
  }
}

// Backend errors come in two shapes:
//   { detail: "string message", code: "..." }  — plain errors
//   { detail: { code, detail, ...extra } }     — structured errors (e.g.
// `image_missing` with the offending image tag attached). The interceptor
// flattens both into a single ApiError shape so callers can branch on
// `code` and access extra fields via `data`.
type ApiErrorData = {
  detail: string | Record<string, unknown>;
  code?: string;
};

export class ApiError extends Error {
  readonly detail: string;
  readonly code: string;
  readonly status: number;
  readonly data: Record<string, unknown> | null;

  constructor(
    detail: string,
    code: string,
    status: number,
    data: Record<string, unknown> | null = null,
  ) {
    super(detail);
    this.name = "ApiError";
    this.detail = detail;
    this.code = code;
    this.status = status;
    this.data = data;
  }
}

// In dev: env.VITE_API_BASE_URL = "http://localhost:17240" → cross-origin to backend (CORS).
// In all-in-one prod: backend serves /config.js with API_BASE_URL = "" → same-origin.
export const apiClient = axios.create({
  baseURL: `${env.VITE_API_BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// Tell the backend (and, via it, the agent/LLM) the current interface language
// on every request. Read live from the store, NOT a hook, so it always reflects
// the user's latest choice. Independent from a project's document language.
apiClient.interceptors.request.use((config) => {
  config.headers.set("X-Interface-Language", useThemeStore.getState().lang);
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status ?? 0;
      const data = error.response?.data as ApiErrorData | undefined;

      let detail: string;
      let code: string;
      let extra: Record<string, unknown> | null = null;

      if (data && typeof data.detail === "object" && data.detail !== null) {
        const obj = data.detail;
        detail =
          typeof obj.detail === "string"
            ? obj.detail
            : (error.message ?? i18n.t("errors:title.generic"));
        code =
          typeof obj.code === "string"
            ? obj.code
            : (data.code ?? "unknown_error");
        extra = obj;
      } else {
        detail =
          typeof data?.detail === "string"
            ? data.detail
            : (error.message ?? i18n.t("errors:message.network"));
        code = data?.code ?? "unknown_error";
      }

      // Auto-toast for mutations and server errors. Skip GET 4xx — callers
      // (e.g. /fs/inspect, /fs/browse) usually render those inline. Also
      // skip 409 (Conflict): we use it for structured "needs user action"
      // errors like image_missing / docker_unavailable, which the UI
      // surfaces inline with proper CTAs.
      const method = (error.config?.method ?? "get").toLowerCase();
      const isReadOnlyClientErr =
        method === "get" && status >= 400 && status < 500;
      const isStructuredConflict = status === 409;
      // Codes-on-FE: if the backend sent a stable error `code` we have a
      // translation for, show the localized message; otherwise fall back to the
      // backend `detail` (which may be Russian — un-coded errors are localized
      // incrementally as codes are added at their raise sites).
      const codeKey = `errors:code.${code}`;
      const message = i18n.exists(codeKey)
        ? i18n.t(codeKey, extra ?? {})
        : detail;
      const silent = error.config?.silentError === true;
      if (silent) {
        // Ошибка всё равно доезжает до вызывающего — молчит только тост.
      } else if (
        !isReadOnlyClientErr &&
        !isStructuredConflict &&
        status !== 0
      ) {
        toast.error(message, i18n.t("errors:title.withStatus", { status }));
      } else if (status === 0) {
        // Network failure (CORS, DNS, server down) — always notify.
        toast.error(message, i18n.t("errors:title.network"));
      }

      return Promise.reject(new ApiError(detail, code, status, extra));
    }
    return Promise.reject(
      error instanceof Error ? error : new Error(String(error)),
    );
  },
);
