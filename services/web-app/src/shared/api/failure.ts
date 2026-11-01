import { ApiError } from "./client";

/**
 * Код отказа для экранов без сессии: код каталога ошибок, "network" при
 * недоступном сервере и "unknown" для всего остального.
 */
export const failureCode = (error: unknown): string => {
  if (error instanceof ApiError)
    return error.status === 0 ? "network" : error.code;
  return "unknown";
};
