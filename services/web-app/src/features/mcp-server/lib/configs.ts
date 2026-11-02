import type { McpTool, McpToolGroup } from "../api/schemas";

/** Подстановка вместо настоящего токена: значение токена показывается один раз при выпуске. */
export const TOKEN_PLACEHOLDER = "hsd_pat_...";

export type ClientConfig = {
  id: "claudeCode" | "cursor" | "vscode" | "stdio";
  /** Язык подсветки: команда или JSON. */
  kind: "shell" | "json";
  text: string;
};

/** Адрес сервера по корню Студии: `https://studio.example.org` + `/mcp`. */
export const endpointUrl = (origin: string, path: string): string =>
  `${origin.replace(/\/+$/, "")}${path}`;

const json = (value: unknown): string => JSON.stringify(value, null, 2);

/**
 * Готовые конфиги популярных клиентов. Облаку нужен токен (заголовок
 * Authorization), локальной Студии нет: она отвечает только этой машине.
 */
export const clientConfigs = (
  url: string,
  withToken: boolean,
): readonly ClientConfig[] => {
  const headers = withToken
    ? { Authorization: `Bearer ${TOKEN_PLACEHOLDER}` }
    : undefined;
  const server = headers ? { url, headers } : { url };
  const origin = url.replace(/\/mcp$/, "");
  const claude = [
    `claude mcp add --transport http hse-doc-studio ${url}`,
    ...(withToken
      ? [`  --header "Authorization: Bearer ${TOKEN_PLACEHOLDER}"`]
      : []),
  ].join(" \\\n");
  const stdio = {
    mcpServers: {
      "hse-doc-studio": {
        command: "hse-doc-studio",
        args: withToken ? ["mcp", "--url", origin] : ["mcp"],
        ...(withToken ? { env: { HSE_STUDIO_TOKEN: TOKEN_PLACEHOLDER } } : {}),
      },
    },
  };
  return [
    { id: "claudeCode", kind: "shell", text: claude },
    {
      id: "cursor",
      kind: "json",
      text: json({ mcpServers: { "hse-doc-studio": server } }),
    },
    {
      id: "vscode",
      kind: "json",
      text: json({
        servers: { "hse-doc-studio": { type: "http", ...server } },
      }),
    },
    { id: "stdio", kind: "json", text: json(stdio) },
  ];
};

export const GROUP_ORDER: readonly McpToolGroup[] = [
  "account",
  "projects",
  "files",
  "build",
  "checks",
  "review",
  "history",
  "submission",
  "admin",
];

/** Тулы по группам в порядке каталога; пустые группы (серверные в локальной Студии) пропускаются. */
export const groupTools = (
  tools: readonly McpTool[],
): { group: McpToolGroup; tools: McpTool[] }[] =>
  GROUP_ORDER.map((group) => ({
    group,
    tools: tools.filter((tool) => tool.group === group),
  })).filter((entry) => entry.tools.length > 0);

/** Новый список выключенных имён после переключения одного элемента. */
export const toggled = <T extends string>(
  list: readonly T[],
  item: T,
  on: boolean,
): T[] =>
  on ? [...new Set([...list, item])] : list.filter((value) => value !== item);
