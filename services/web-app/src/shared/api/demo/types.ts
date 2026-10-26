import type { AxiosResponse } from "axios";

export type DemoMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

// Один запрос, как его видит обработчик: путь без базового адреса и без query.
export type DemoRequest = {
  method: DemoMethod;
  path: string;
  // Параметры маршрута вида /projects/:projectId/git.
  params: Record<string, string>;
  // Значения query (axios params и часть после ? в адресе); повторы дают массив.
  query: Record<string, string | string[]>;
  // JSON-тело уже разобрано; multipart приходит как FormData.
  body: unknown;
  // Отправить запрос настоящему бэкенду: нужно, чтобы дополнить его ответ.
  forward: () => Promise<AxiosResponse>;
};

export type DemoResponse = {
  status: number;
  data?: unknown;
  headers?: Record<string, string>;
};

export type DemoHandler = (
  req: DemoRequest,
) => DemoResponse | Promise<DemoResponse>;

export type DemoRoute = {
  method: DemoMethod;
  pattern: string;
  handler: DemoHandler;
};
