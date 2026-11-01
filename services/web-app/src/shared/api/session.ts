// Состояние сессии, нужное транспортному слою: CSRF-токен и реакция на 401.
// Живёт в shared, потому что клиент не вправе знать про слой entities; токен и
// обработчик туда кладёт entities/session и приложение.

let csrfToken: string | null = null;

export const getCsrfToken = (): string | null => csrfToken;

export const setCsrfToken = (token: string | null): void => {
  csrfToken = token;
};

type UnauthorizedHandler = () => Promise<unknown> | undefined;

let unauthorizedHandler: UnauthorizedHandler | null = null;
let notifying = false;

export const setUnauthorizedHandler = (
  handler: UnauthorizedHandler | null,
): void => {
  unauthorizedHandler = handler;
};

// Запросы, чей 401 обработчика не будит: иначе обновление bootstrap само
// порождало бы 401 и зацикливалось, а неверный пароль выглядел бы как конец сессии.
const isAuthProbe = (url: string): boolean => {
  const path = url.split("?")[0] ?? "";
  return path.endsWith("/session/bootstrap") || /(^|\/)auth\//.test(path);
};

/**
 * Клиент получил 401. Обработчик (обновить bootstrap) вызывается не чаще одного
 * раза за раз: пачка параллельных запросов с протухшей сессией даёт один
 * перезапрос, а не лавину.
 */
export const notifyUnauthorized = (url: string): void => {
  if (unauthorizedHandler === null || notifying || isAuthProbe(url)) return;
  notifying = true;
  const done = () => {
    notifying = false;
  };
  try {
    void Promise.resolve(unauthorizedHandler()).then(done, done);
  } catch {
    done();
  }
};
