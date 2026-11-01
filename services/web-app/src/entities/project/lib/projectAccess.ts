import { ApiError } from "@shared/api";

/**
 * Проект недоступен: сервер отвечает 404 и на чужой, и на несуществующий, чтобы
 * не выдавать, что он есть. Причины экран не различает.
 */
export const isProjectUnavailable = (error: unknown): boolean =>
  error instanceof ApiError && error.status === 404;
