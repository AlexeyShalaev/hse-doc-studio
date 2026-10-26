import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import type { DemoMethod, DemoRequest } from "./types";
import type { DemoRouter } from "./router";

export type DemoAdapterOptions = {
  // Задержка ответа, мс: чтобы спиннеры и состояния загрузки успевали показаться.
  latencyMs?: number;
};

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

const splitUrl = (url: string): { path: string; query: string } => {
  const index = url.indexOf("?");
  return index === -1
    ? { path: url, query: "" }
    : { path: url.slice(0, index), query: url.slice(index + 1) };
};

const addQuery = (
  target: Record<string, string | string[]>,
  key: string,
  value: string,
): void => {
  const current = target[key];
  if (current === undefined) target[key] = value;
  else if (Array.isArray(current)) current.push(value);
  else target[key] = [current, value];
};

const collectQuery = (
  config: InternalAxiosRequestConfig,
  inline: string,
): Record<string, string | string[]> => {
  const result: Record<string, string | string[]> = {};
  new URLSearchParams(inline).forEach((value, key) => {
    addQuery(result, key, value);
  });
  const params: unknown = config.params;
  if (params !== null && typeof params === "object") {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      const items: unknown[] = Array.isArray(value) ? value : [value];
      for (const item of items) {
        addQuery(result, key, String(item));
      }
    }
  }
  return result;
};

const parseBody = (data: unknown): unknown => {
  if (typeof data !== "string" || data === "") return data ?? null;
  try {
    return JSON.parse(data) as unknown;
  } catch {
    return data;
  }
};

const resolveFallback = (client: AxiosInstance): AxiosAdapter =>
  axios.getAdapter(client.defaults.adapter);

// Сырой адаптер отдаёт тело строкой: JSON разбирает уже axios после адаптера, а
// обработчик демо-маршрута, запросивший forward(), ждёт готовый объект.
const parseForwarded = (response: AxiosResponse): AxiosResponse => {
  if (typeof response.data !== "string" || response.data === "")
    return response;
  try {
    return { ...response, data: JSON.parse(response.data) as unknown };
  } catch {
    return response;
  }
};

/**
 * Подменяет транспорт axios: маршруты из таблицы отвечают сами, всё остальное
 * уходит настоящему бэкенду. Так демо-режим оживляет только то, чего ещё нет на
 * сервере, и не ломает остальное приложение.
 */
export const installDemoAdapter = (
  client: AxiosInstance,
  router: DemoRouter,
  options: DemoAdapterOptions = {},
): void => {
  const fallback = resolveFallback(client);
  const latency = options.latencyMs ?? 0;

  const adapter: AxiosAdapter = async (config) => {
    const { path, query } = splitUrl(config.url ?? "");
    const method = (config.method ?? "get").toUpperCase();
    const found = router.match(method, path);
    if (!found) return fallback(config);

    const request: DemoRequest = {
      method: method as DemoMethod,
      path,
      params: found.params,
      query: collectQuery(config, query),
      body: parseBody(config.data),
      forward: () => fallback(config).then(parseForwarded),
    };
    const response = await found.handler(request);
    if (latency > 0) await sleep(latency);

    const result: AxiosResponse = {
      data: response.data,
      status: response.status,
      statusText: String(response.status),
      headers: response.headers ?? {},
      config,
      request: {},
    };
    if (response.status >= 400) {
      throw new AxiosError(
        `Request failed with status code ${String(response.status)}`,
        response.status >= 500
          ? AxiosError.ERR_BAD_RESPONSE
          : AxiosError.ERR_BAD_REQUEST,
        config,
        result.request,
        result,
      );
    }
    return result;
  };

  client.defaults.adapter = adapter;
};
