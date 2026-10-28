import { safeNextPath, type Bootstrap } from "@entities/session";

// Экраны, доступные без входа. Остальное в серверном режиме требует сессии.
const PUBLIC_EXACT = ["/login", "/register", "/forgot", "/first-run"];
const PUBLIC_PREFIXES = ["/invite/", "/verify/", "/reset/", "/auth/"];
// Экраны только для гостей: вошедшему человеку на них делать нечего.
const GUEST_ONLY = ["/login", "/register", "/forgot"];

// React Router сопоставляет адреса без учёта регистра (/Login открывает вход),
// поэтому и шлюз сравнивает в нижнем регистре.
const trimSlash = (path: string): string =>
  (path.length > 1 && path.endsWith("/")
    ? path.slice(0, -1)
    : path
  ).toLowerCase();

export const isPublicPath = (pathname: string): boolean => {
  const path = trimSlash(pathname);
  return (
    PUBLIC_EXACT.includes(path) ||
    PUBLIC_PREFIXES.some((prefix) => path.startsWith(prefix))
  );
};

// Страницы разработчика (галереи состояний) живут вне сессии, но только в dev-сборке.
const isDevPath = (pathname: string): boolean =>
  import.meta.env.DEV && pathname.toLowerCase().startsWith("/dev/");

export type GateLocation = { pathname: string; search: string; hash: string };

/**
 * Куда отправить человека в серверном режиме, или null, если остаться.
 * В локальном режиме шлюз только уводит с экранов входа на главную.
 * Чистая функция: все решения шлюза читаются и проверяются в одном месте.
 *
 * - мастер первого запуска не пройден: на /first-run с любого адреса;
 * - гость на закрытом адресе: на /login, с ?next= на то, куда он шёл;
 * - вошедший на экране для гостей: на next (проверенный) или на главную;
 * - вошедший на /first-run после настройки: на главную.
 */
export const resolveGateRedirect = (
  bootstrap: Bootstrap,
  location: GateLocation,
): string | null => {
  const path = trimSlash(location.pathname);
  // Локальный режим без входа: экраны сессии ему не нужны, адрес как раньше
  // вёл бы на 404, а теперь ведёт на главную.
  if (bootstrap.mode !== "server") {
    return isPublicPath(path) ? "/" : null;
  }

  if (bootstrap.setup_state === "needs_admin") {
    return path === "/first-run" ? null : "/first-run";
  }
  if (isDevPath(location.pathname)) return null;

  if (bootstrap.user === null) {
    if (isPublicPath(path) && path !== "/first-run") return null;
    const target = `${location.pathname}${location.search}${location.hash}`;
    const next = safeNextPath(target, "");
    return next === "" || next === "/"
      ? "/login"
      : `/login?next=${encodeURIComponent(next)}`;
  }

  if (path === "/first-run") return "/";
  if (GUEST_ONLY.includes(path)) {
    return safeNextPath(new URLSearchParams(location.search).get("next"));
  }
  return null;
};
