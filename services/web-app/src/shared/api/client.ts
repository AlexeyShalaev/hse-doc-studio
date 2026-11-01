import axios, { type AxiosInstance } from "axios";
import { env } from "@shared/config";
import { toast, i18n, useThemeStore } from "@shared/lib";
import { getCsrfToken, notifyUnauthorized } from "./session";

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
//
// The git-sync endpoints use a third, FLAT shape: `{ detail: "string", code,
// ...extra }` (`operation_id`, `projects`, `paths`, `host_keys`, ...). For it
// `data` carries everything except `detail` and `code`, so callers can read the
// extras and `errors:code.*` strings get their interpolation values.
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

// Тело ошибки запроса с responseType "blob" приходит Blob-ом: читаем его как
// JSON, чтобы код и подробности не терялись. Не JSON и не Blob — как есть.
const readBlobText = (blob: Blob): Promise<string> => {
  if (typeof blob.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(new Error("blob read failed"));
    };
    reader.readAsText(blob);
  });
};

const decodeBlobBody = async (data: unknown): Promise<unknown> => {
  if (typeof Blob === "undefined" || !(data instanceof Blob)) return data;
  try {
    return JSON.parse(await readBlobText(data)) as unknown;
  } catch {
    return undefined;
  }
};

const UNSAFE_METHODS = new Set(["post", "put", "patch", "delete"]);

export type ApiClientOptions = {
  // Полный базовый адрес: хост (в dev бэкенд на другом порту) плюс префикс API.
  baseURL: string;
  timeout?: number;
};

/**
 * Фабрика клиентов: общий разбор ошибок, язык интерфейса, куки сессии и
 * CSRF-токен. Клиентов два: `apiClient` (/api/v1) и `adminClient` (/api/admin),
 * у них одна политика ошибок и одна сессия.
 */
export const createApiClient = (options: ApiClientOptions): AxiosInstance => {
  const client = axios.create({
    baseURL: options.baseURL,
    headers: { "Content-Type": "application/json" },
    timeout: options.timeout ?? 30_000,
    // Несколько значений фильтра уходят повтором параметра (status=a&status=b),
    // как их ждёт FastAPI, а не в виде status[]=a.
    paramsSerializer: { indexes: null },
    // Серверный режим держит сессию в HttpOnly-куке. В локальном режиме кук нет,
    // флаг ничего не меняет.
    withCredentials: true,
  });

  // Tell the backend (and, via it, the agent/LLM) the current interface language
  // on every request. Read live from the store, NOT a hook, so it always reflects
  // the user's latest choice. Independent from a project's document language.
  client.interceptors.request.use((config) => {
    config.headers.set("X-Interface-Language", useThemeStore.getState().lang);
    // CSRF: токен привязан к сессии и приходит в bootstrap/login. Небезопасным
    // методам он обязателен, безопасным не нужен. Bearer-запросам (CLI) тоже,
    // но их в браузере нет.
    const csrf = getCsrfToken();
    if (
      csrf !== null &&
      UNSAFE_METHODS.has((config.method ?? "get").toLowerCase())
    ) {
      config.headers.set("X-CSRF-Token", csrf);
    }
    return config;
  });

  client.interceptors.response.use(
    (res) => res,
    async (error: unknown) => {
      if (axios.isAxiosError(error)) {
        const status = error.response?.status ?? 0;
        const data = (await decodeBlobBody(error.response?.data)) as
          ApiErrorData | undefined;

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
          if (data && typeof data === "object" && !Array.isArray(data)) {
            const { detail: _detail, code: _code, ...flat } = data;
            if (Object.keys(flat).length > 0) extra = flat;
          }
        }

        // Retry-After (429) в секундах: форма входа показывает обратный отсчёт.
        const retryHeader: unknown = error.response?.headers?.["retry-after"];
        const retryAfter =
          typeof retryHeader === "string"
            ? Number.parseInt(retryHeader, 10)
            : NaN;
        if (Number.isFinite(retryAfter) && retryAfter > 0) {
          extra = { ...extra, retry_after: retryAfter };
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
        const roleNamed =
          code === "forbidden_role" && typeof extra?.required_role === "string";
        // Без названия роли отказ по роли читается как обычный отказ.
        const codeKey =
          code === "forbidden_role" && !roleNamed
            ? "errors:code.forbidden"
            : `errors:code.${code}`;
        // Отказ по роли называет нужную роль словами интерфейса, а не кодом.
        const params =
          roleNamed && typeof extra?.required_role === "string"
            ? {
                ...extra,
                role: i18n.t(`projectAccess:roles.${extra.required_role}`),
              }
            : (extra ?? {});
        const message = i18n.exists(codeKey) ? i18n.t(codeKey, params) : detail;
        const silent = error.config?.silentError === true;
        if (status === 401) {
          // Сессия кончилась или её нет: это не ошибка для тоста. Форма входа
          // показывает отказ сама, остальное узнаёт из обновлённого bootstrap.
          notifyUnauthorized(error.config?.url ?? "");
        } else if (silent) {
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

        // Токен CSRF устарел (сессию пересоздали в другой вкладке): свежий лежит в
        // bootstrap, обновление его подтянет. Тост остаётся: действие не прошло.
        if (status === 403 && code === "csrf_failed") {
          notifyUnauthorized(error.config?.url ?? "");
        }

        return Promise.reject(new ApiError(detail, code, status, extra));
      }
      return Promise.reject(
        error instanceof Error ? error : new Error(String(error)),
      );
    },
  );

  return client;
};

// In dev: env.VITE_API_BASE_URL = "http://localhost:17240" → cross-origin to backend (CORS).
// In all-in-one prod: backend serves /config.js with API_BASE_URL = "" → same-origin.
export const apiClient = createApiClient({
  baseURL: `${env.VITE_API_BASE_URL}/api/v1`,
});

// Админка установки: тот же транспорт и та же сессия, другой префикс.
export const adminClient = createApiClient({
  baseURL: `${env.VITE_API_BASE_URL}/api/admin`,
});
