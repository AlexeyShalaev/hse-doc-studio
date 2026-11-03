// Адреса пути «облако → локальная Студия» (docs/design/local-from-cloud.md).
// Маршруты стабильные: на них ссылаются справка, онбординг и подсказка
// «облачная сборка недоступна», меняйте их только вместе с этими местами.

/** Экран «Локальная версия» облачной Студии. */
export const LOCAL_STUDIO_PATH = "/local-studio";
/** Экран «Подключиться к серверу» локальной Студии. */
export const CONNECT_SERVER_PATH = "/connect";
/** Порт локальной Студии по умолчанию (deploy/install.sh). */
export const DEFAULT_LOCAL_PORT = 17240;

/** Страница документации «Локальная версия из облака» (адрес закреплён в docs/design/local-from-cloud.md). */
export const localFromCloudDocsUrl = (language: string): string =>
  `https://alexeyshalaev.github.io/hse-doc-studio/${language.startsWith("en") ? "en/" : ""}start/local-from-cloud/`;

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isProjectId = (value: string): boolean => UUID_RE.test(value);

export const isValidPort = (port: number): boolean =>
  Number.isInteger(port) && port >= 1 && port <= 65535;

/** Экран «Локальная версия»; с проектом он покажет «Открыть этот проект». */
export const localStudioPath = (projectId?: string | null): string =>
  projectId
    ? `${LOCAL_STUDIO_PATH}?${new URLSearchParams({ project: projectId }).toString()}`
    : LOCAL_STUDIO_PATH;

/** Что подключать: адрес сервера и, если нужно, проект на нём. */
export type ConnectTarget = { server: string | null; projectId: string | null };

const connectQuery = (target: ConnectTarget): string => {
  const params = new URLSearchParams();
  if (target.server) params.set("server", target.server);
  if (target.projectId) params.set("project", target.projectId);
  const query = params.toString();
  return query ? `?${query}` : "";
};

/** Экран подключения внутри локальной Студии. */
export const connectServerPath = (
  target: ConnectTarget = { server: null, projectId: null },
): string => `${CONNECT_SERVER_PATH}${connectQuery(target)}`;

/** Сервер и проект из строки запроса экрана подключения; мусор отбрасывается. */
export const readConnectTarget = (params: URLSearchParams): ConnectTarget => {
  const server = params.get("server")?.trim() ?? "";
  const project = params.get("project")?.trim() ?? "";
  return {
    server: server === "" ? null : server,
    projectId: isProjectId(project) ? project : null,
  };
};

/**
 * Ссылка из облака в локальную Студию на этом компьютере: открывает её экран
 * подключения с готовым адресом сервера (и проектом).
 */
export const localConnectUrl = (
  port: number,
  server: string,
  projectId: string | null = null,
): string =>
  `http://localhost:${String(port)}${connectServerPath({ server: server.replace(/\/+$/, ""), projectId })}`;

/** Адрес клонирования проекта на сервере Студии (`<сервер>/git/<id>.git`). */
export const studioCloneUrl = (server: string, projectId: string): string =>
  `${server.replace(/\/+$/, "")}/git/${projectId}.git`;
