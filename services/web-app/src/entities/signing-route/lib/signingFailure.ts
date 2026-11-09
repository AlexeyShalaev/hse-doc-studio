import { ApiError, failureCode } from "@shared/api";

/** Отказ действия подписанта: код с текстом в словаре `signing` (`failure.*`) или `unknown`. */
export type SigningFailure = {
  code: string;
  /** Пояснение сервера к отказу без своего текста. */
  detail: string | null;
};

/**
 * Коды отказов страницы подписанта, у которых есть свой текст (`failure.<код>`): раздел 8.1
 * дизайна и коды подписи ключом Студии (пароль, ключ, политика хранения ключей).
 */
export const SIGNING_TASK_FAILURE_CODES: readonly string[] = [
  "doc_changed",
  "not_your_turn",
  "image_required",
  "plate_required",
  "method_not_allowed",
  "passphrase_required",
  "passphrase_invalid",
  "key_not_found",
  "server_keys_forbidden",
  "route_locked",
  "not_found",
  "network",
];

/** Во что превратить ошибку запроса: известный код или `unknown` с пояснением сервера. */
export const signingFailureOf = (error: unknown): SigningFailure => {
  const code = failureCode(error);
  if (SIGNING_TASK_FAILURE_CODES.includes(code)) return { code, detail: null };
  // Пояснение сервера полезнее, чем «не получилось», но у 5xx оно ни о чём.
  const detail =
    error instanceof ApiError && error.status >= 400 && error.status < 500
      ? error.detail.trim()
      : "";
  return { code: "unknown", detail: detail === "" ? null : detail };
};
