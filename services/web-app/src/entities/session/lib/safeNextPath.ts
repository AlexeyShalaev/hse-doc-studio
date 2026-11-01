// Адрес возврата после входа (?next=). Принимаем только путь внутри приложения:
// всё, что браузер может истолковать как другой хост или схему, отбрасываем,
// иначе форма входа превращается в открытый редирект для фишинга.

export const DEFAULT_NEXT_PATH = "/";

const MAX_LENGTH = 2048;
// Управляющие символы, обратная косая и пробельные: браузеры вычищают табы и
// переводы строк из URL, и "/\t/evil.com" превращается в "//evil.com".
// eslint-disable-next-line no-control-regex
const FORBIDDEN = /[\u0000-\u001f\u007f\\\s]/;
// Страницы входа и служебные адреса сервера: возврат на них ничего не даёт или зацикливает.
const BLOCKED_PREFIXES = ["/login", "/register", "/auth", "/api", "/first-run"];

// Без учёта регистра: роутер открывает /Login так же, как /login.
const isBlocked = (rawPath: string): boolean => {
  const path = rawPath.toLowerCase();
  return BLOCKED_PREFIXES.some((prefix) => {
    if (!path.startsWith(prefix)) return false;
    const next = path.charAt(prefix.length);
    return next === "" || next === "/" || next === "?" || next === "#";
  });
};

const decodeOnce = (value: string): string | null => {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
};

/**
 * Возвращает безопасный внутренний путь или `fallback`.
 * Кодированные обходы (`/%2F/evil.com`, `/%5Cevil.com`) ловятся проверкой
 * декодированной формы.
 */
export const safeNextPath = (
  raw: string | null | undefined,
  fallback: string = DEFAULT_NEXT_PATH,
): string => {
  if (typeof raw !== "string" || raw === "" || raw.length > MAX_LENGTH) {
    return fallback;
  }
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  if (FORBIDDEN.test(raw)) return fallback;
  const decoded = decodeOnce(raw);
  if (decoded === null) return fallback;
  if (decoded.startsWith("//") || FORBIDDEN.test(decoded)) return fallback;
  if (isBlocked(raw) || isBlocked(decoded)) return fallback;
  return raw;
};
