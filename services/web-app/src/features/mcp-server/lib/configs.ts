import type { McpTool, McpToolGroup } from "../api/schemas";

/** Подстановка вместо настоящего токена: значение токена показывается один раз при выпуске. */
export const TOKEN_PLACEHOLDER = "hsd_pat_...";

/** Переменная окружения с токеном: её читают мост `hse-doc-studio mcp` и конфиги клиентов. */
export const TOKEN_ENV = "HSE_STUDIO_TOKEN";

export const CLIENT_IDS = [
  "claudeCode",
  "codex",
  "opencode",
  "gemini",
  "cursor",
  "vscode",
  "windsurf",
  "zed",
  "cline",
  "junie",
  "stdio",
] as const;

export type ClientId = (typeof CLIENT_IDS)[number];

export type ClientConfig = {
  id: ClientId;
  /** Язык подсветки: команда, JSON или TOML. */
  kind: "shell" | "json" | "toml";
  text: string;
  /** Конфиг берёт токен из переменной TOKEN_ENV, а не хранит его в файле. */
  tokenFromEnv: boolean;
  /** Официальная страница клиента про MCP. */
  docs: string;
};

/** Адрес сервера по корню Студии: `https://studio.example.org` + `/mcp`. */
export const endpointUrl = (origin: string, path: string): string =>
  `${origin.replace(/\/+$/, "")}${path}`;

const json = (value: unknown): string => JSON.stringify(value, null, 2);

const NAME = "hse-doc-studio";

/**
 * Готовые конфиги популярных клиентов. Облаку нужен токен (заголовок
 * Authorization), локальной Студии нет: она отвечает только этой машине.
 * Где клиент умеет подставлять переменную окружения, токен берётся из
 * TOKEN_ENV и в файл не попадает. Форматы сверены с документацией клиентов
 * (ссылки в `docs`).
 */
export const clientConfigs = (
  url: string,
  withToken: boolean,
): readonly ClientConfig[] => {
  const bearer = (token: string) =>
    withToken ? { headers: { Authorization: `Bearer ${token}` } } : {};
  const plain = bearer(TOKEN_PLACEHOLDER);
  const origin = url.replace(/\/mcp$/, "");
  const command = (...lines: (string | false)[]): string =>
    lines.filter((line): line is string => line !== false).join(" \\\n  ");
  const config = (
    id: ClientId,
    kind: ClientConfig["kind"],
    text: string,
    docs: string,
    tokenFromEnv = false,
  ): ClientConfig => ({
    id,
    kind,
    text,
    docs,
    tokenFromEnv: withToken && tokenFromEnv,
  });
  return [
    config(
      "claudeCode",
      "shell",
      command(
        `claude mcp add --transport http ${NAME} ${url}`,
        withToken && `--header "Authorization: Bearer ${TOKEN_PLACEHOLDER}"`,
      ),
      "https://code.claude.com/docs/en/mcp",
    ),
    config(
      "codex",
      "shell",
      command(
        `codex mcp add ${NAME} --url ${url}`,
        withToken && `--bearer-token-env-var ${TOKEN_ENV}`,
      ),
      "https://developers.openai.com/codex/mcp",
      true,
    ),
    config(
      "opencode",
      "json",
      json({
        $schema: "https://opencode.ai/config.json",
        mcp: {
          servers: {
            [NAME]: {
              type: "remote",
              url,
              oauth: false,
              ...bearer(`{env:${TOKEN_ENV}}`),
            },
          },
        },
      }),
      "https://opencode.ai/docs/mcp-servers/",
      true,
    ),
    config(
      "gemini",
      "json",
      json({
        mcpServers: { [NAME]: { httpUrl: url, ...bearer(`\${${TOKEN_ENV}}`) } },
      }),
      "https://geminicli.com/docs/tools/mcp-server/",
      true,
    ),
    config(
      "cursor",
      "json",
      json({
        mcpServers: { [NAME]: { url, ...bearer(`\${env:${TOKEN_ENV}}`) } },
      }),
      "https://cursor.com/docs/mcp",
      true,
    ),
    config(
      "vscode",
      "json",
      json({
        mcpServers: {
          [NAME]: {
            type: "http",
            url,
            ...bearer(`\${${TOKEN_ENV}}`),
            tools: ["*"],
          },
        },
      }),
      "https://code.visualstudio.com/docs/agents/reference/mcp-configuration",
      true,
    ),
    config(
      "windsurf",
      "json",
      json({
        mcpServers: {
          [NAME]: { serverUrl: url, ...bearer(`\${env:${TOKEN_ENV}}`) },
        },
      }),
      "https://docs.devin.ai/windsurf/plugins/cascade/mcp",
      true,
    ),
    config(
      "zed",
      "json",
      json({ context_servers: { [NAME]: { url, ...plain } } }),
      "https://zed.dev/docs/ai/mcp",
    ),
    config(
      "cline",
      "json",
      json({
        mcpServers: { [NAME]: { type: "streamableHttp", url, ...plain } },
      }),
      "https://docs.cline.bot/mcp/adding-and-configuring-servers",
    ),
    config(
      "junie",
      "json",
      json({ mcpServers: { [NAME]: { url, ...plain } } }),
      "https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html",
    ),
    config(
      "stdio",
      "json",
      json({
        mcpServers: {
          [NAME]: {
            command: NAME,
            args: withToken ? ["mcp", "--url", origin] : ["mcp"],
            ...(withToken ? { env: { [TOKEN_ENV]: TOKEN_PLACEHOLDER } } : {}),
          },
        },
      }),
      "https://modelcontextprotocol.io/docs/develop/connect-local-servers",
    ),
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
