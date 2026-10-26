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
  // Сколько длится каждый из четырёх шагов «загрузки» файла, мс. Без этого
  // индикатор отправки файла не успел бы показаться; по умолчанию равна задержке.
  uploadStepMs?: number;
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

const UPLOAD_STEPS = [0.15, 0.45, 0.75, 1] as const;

// Размер тела запроса, если там файл: по нему рисуем ход загрузки.
const uploadSize = (data: unknown): number => {
  if (data instanceof Blob) return data.size;
  if (data instanceof FormData) {
    let total = 0;
    data.forEach((value) => {
      if (value instanceof Blob) total += value.size;
    });
    return total;
  }
  return 0;
};

const resolveFallback = (client: AxiosInstance): AxiosAdapter =>
  axios.getAdapter(client.defaults.adapter);

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
  const uploadStep = options.uploadStepMs ?? latency;

  // Имитация отправки файла: вызывает onUploadProgress и уважает отмену.
  const simulateUpload = async (
    config: InternalAxiosRequestConfig,
  ): Promise<void> => {
    const report = config.onUploadProgress;
    if (!report || uploadStep <= 0) return;
    const total = uploadSize(config.data);
    if (total === 0) return;
    for (const part of UPLOAD_STEPS) {
      await sleep(uploadStep);
      if (config.signal?.aborted)
        throw new axios.CanceledError(undefined, config);
      const loaded = Math.round(total * part);
      report({
        loaded,
        total,
        bytes: loaded,
        progress: part,
        lengthComputable: true,
        upload: true,
      });
    }
  };

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
      forward: () => fallback(config),
    };
    if (config.signal?.aborted) {
      throw new axios.CanceledError(undefined, config);
    }
    await simulateUpload(config);
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
