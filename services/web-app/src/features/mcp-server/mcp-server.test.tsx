import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import { mcpApi } from "./api/mcpApi";
import type { McpInfo, McpSettings, McpTool } from "./api/schemas";
import {
  CLIENT_IDS,
  TOKEN_ENV,
  TOKEN_PLACEHOLDER,
  clientConfigs,
  groupTools,
  toggled,
} from "./lib/configs";
import { ensureAdminMcpLocales } from "./lib/locales";
import { AdminMcpPage } from "./ui/AdminMcpPage";
import { McpSection } from "./ui/McpSection";

const tool = (patch: Partial<McpTool> = {}): McpTool => ({
  name: "read_tex",
  group: "files",
  kind: "read",
  description: "Прочитать файл",
  dangerous: false,
  admin: false,
  enabled: true,
  ...patch,
});

const settings = (patch: Partial<McpSettings> = {}): McpSettings => ({
  enabled: true,
  disabled_tools: [],
  disabled_groups: ["admin"],
  enabled_dangerous: [],
  endpoint_path: "/mcp",
  tools: [
    tool(),
    tool({
      name: "delete_file",
      kind: "write",
      dangerous: true,
      enabled: false,
    }),
    tool({ name: "list_projects", group: "projects" }),
  ],
  ...patch,
});

const info = (patch: Partial<McpInfo> = {}): McpInfo => ({
  enabled: true,
  mode: "server",
  endpoint_path: "/mcp",
  token_scope: "mcp",
  tools: ["list_projects", "read_tex"],
  ...patch,
});

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

describe("конфиги и группы: чистая логика", () => {
  it("облаку нужен токен в заголовке, локальной Студии нет", () => {
    const cloud = clientConfigs("https://s.example/mcp", true);
    const local = clientConfigs("http://127.0.0.1:17240/mcp", false);
    expect(cloud.find((c) => c.id === "cursor")?.text).toContain(
      "Authorization",
    );
    expect(local.find((c) => c.id === "cursor")?.text).not.toContain(
      "Authorization",
    );
    expect(cloud.find((c) => c.id === "stdio")?.text).toContain(
      "https://s.example",
    );
  });

  it("у каждого клиента свой конфиг и официальная ссылка", () => {
    const cloud = clientConfigs("https://s.example/mcp", true);
    expect(cloud.map((c) => c.id)).toEqual([...CLIENT_IDS]);
    for (const config of cloud) {
      expect(config.docs).toMatch(/^https:\/\//);
      if (config.kind === "json")
        expect(() => {
          JSON.parse(config.text);
        }).not.toThrow();
    }
  });

  it("токен из переменной окружения, где клиент это умеет", () => {
    const cloud = clientConfigs("https://s.example/mcp", true);
    const fromEnv = cloud.filter((c) => c.tokenFromEnv).map((c) => c.id);
    expect(fromEnv).toEqual([
      "codex",
      "opencode",
      "gemini",
      "cursor",
      "vscode",
      "windsurf",
    ]);
    for (const config of cloud) {
      if (config.tokenFromEnv) {
        expect(config.text).toContain(TOKEN_ENV);
        expect(config.text).not.toContain(TOKEN_PLACEHOLDER);
      } else {
        expect(config.text).toContain(TOKEN_PLACEHOLDER);
      }
    }
  });

  it("локальной Студии ни токен, ни переменная не нужны", () => {
    for (const config of clientConfigs("http://127.0.0.1:17240/mcp", false)) {
      expect(config.tokenFromEnv).toBe(false);
      expect(config.text).not.toContain("Authorization");
      expect(config.text).not.toContain(TOKEN_ENV);
      expect(config.text).not.toContain("bearer");
    }
  });

  it("эталоны форматов: Codex, OpenCode, Gemini CLI, Windsurf, VS Code", () => {
    const byId = Object.fromEntries(
      clientConfigs("https://s.example/mcp", true).map((c) => [c.id, c.text]),
    );
    expect(byId.codex).toBe(
      "codex mcp add hse-doc-studio --url https://s.example/mcp \\\n" +
        "  --bearer-token-env-var HSE_STUDIO_TOKEN",
    );
    expect(JSON.parse(byId.opencode ?? "")).toEqual({
      $schema: "https://opencode.ai/config.json",
      mcp: {
        servers: {
          "hse-doc-studio": {
            type: "remote",
            url: "https://s.example/mcp",
            oauth: false,
            headers: { Authorization: "Bearer {env:HSE_STUDIO_TOKEN}" },
          },
        },
      },
    });
    expect(JSON.parse(byId.gemini ?? "")).toEqual({
      mcpServers: {
        "hse-doc-studio": {
          httpUrl: "https://s.example/mcp",
          headers: { Authorization: "Bearer ${HSE_STUDIO_TOKEN}" },
        },
      },
    });
    expect(JSON.parse(byId.windsurf ?? "")).toEqual({
      mcpServers: {
        "hse-doc-studio": {
          serverUrl: "https://s.example/mcp",
          headers: { Authorization: "Bearer ${env:HSE_STUDIO_TOKEN}" },
        },
      },
    });
    expect(JSON.parse(byId.vscode ?? "")).toEqual({
      mcpServers: {
        "hse-doc-studio": {
          type: "http",
          url: "https://s.example/mcp",
          headers: { Authorization: "Bearer ${HSE_STUDIO_TOKEN}" },
          tools: ["*"],
        },
      },
    });
    expect(JSON.parse(byId.zed ?? "")).toEqual({
      context_servers: {
        "hse-doc-studio": {
          url: "https://s.example/mcp",
          headers: { Authorization: "Bearer hsd_pat_..." },
        },
      },
    });
  });

  it("группы идут в порядке каталога и без пустых", () => {
    const groups = groupTools(settings().tools).map((g) => g.group);
    expect(groups).toEqual(["projects", "files"]);
  });

  it("переключение добавляет и убирает имя один раз", () => {
    expect(toggled(["a"], "a", true)).toEqual(["a"]);
    expect(toggled(["a", "b"], "a", false)).toEqual(["b"]);
  });
});

describe("MCP в интерфейсе", () => {
  beforeAll(async () => {
    // Radix Select ловит указатель; в jsdom этих методов нет.
    const proto = Element.prototype as Partial<Element> & {
      hasPointerCapture?: (id: number) => boolean;
      releasePointerCapture?: (id: number) => void;
      scrollIntoView?: () => void;
    };
    proto.hasPointerCapture ??= () => false;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
    await ensureAdminMcpLocales();
    await i18n.changeLanguage("ru");
  });

  beforeEach(() => {
    vi.spyOn(mcpApi, "calls").mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("админка: опасный тул включается поимённо", async () => {
    vi.spyOn(mcpApi, "settings").mockResolvedValue(settings());
    const save = vi
      .spyOn(mcpApi, "save")
      .mockResolvedValue(settings({ enabled_dangerous: ["delete_file"] }));
    render(wrap(<AdminMcpPage />));

    await userEvent.click(await screen.findByTestId("mcp-tool-delete_file"));

    await waitFor(() => {
      expect(save).toHaveBeenCalledWith("admin", {
        enabled_dangerous: ["delete_file"],
        disabled_tools: [],
      });
    });
    expect(screen.getByText("MCP-сервер")).toBeInTheDocument();
  });

  it("админка: общий переключатель выключает сервер", async () => {
    vi.spyOn(mcpApi, "settings").mockResolvedValue(settings());
    const save = vi
      .spyOn(mcpApi, "save")
      .mockResolvedValue(settings({ enabled: false }));
    render(wrap(<AdminMcpPage />));

    await userEvent.click(await screen.findByTestId("mcp-enabled"));

    await waitFor(() => {
      expect(save).toHaveBeenCalledWith("admin", { enabled: false });
    });
  });

  it("облако: конфиги с токеном и список доступных тулов", async () => {
    vi.spyOn(mcpApi, "info").mockResolvedValue(info());
    render(wrap(<McpSection />));

    expect(await screen.findByTestId("mcp-connect")).toBeInTheDocument();
    expect(screen.getByText("read_tex")).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-settings")).not.toBeInTheDocument();
  });

  it("облако: выбор клиента показывает его конфиг, подсказку и ссылку", async () => {
    vi.spyOn(mcpApi, "info").mockResolvedValue(info());
    render(wrap(<McpSection />));

    const value = (label: string): string =>
      screen.getByLabelText<HTMLTextAreaElement>(label).value;
    await screen.findByLabelText("Claude Code");
    expect(value("Claude Code")).toContain("claude mcp add");
    await userEvent.click(screen.getByRole("combobox", { name: "Клиент" }));
    await userEvent.click(
      await screen.findByRole("option", {
        name: "OpenAI Codex (CLI, IDE, приложение)",
      }),
    );

    expect(value("OpenAI Codex (CLI, IDE, приложение)")).toContain(
      "--bearer-token-env-var HSE_STUDIO_TOKEN",
    );
    const note = screen.getByTestId("mcp-connect-note");
    expect(note).toHaveTextContent("HSE_STUDIO_TOKEN");
    expect(
      screen.getByRole("link", { name: "Документация клиента" }),
    ).toHaveAttribute("href", "https://developers.openai.com/codex/mcp");
  });

  it("облако: выключенный админом MCP так и называется", async () => {
    vi.spyOn(mcpApi, "info").mockResolvedValue(
      info({ enabled: false, tools: [] }),
    );
    render(wrap(<McpSection />));

    expect(await screen.findByTestId("mcp-off")).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-connect")).not.toBeInTheDocument();
  });

  it("локально: настройки и конфиги без токена", async () => {
    vi.spyOn(mcpApi, "info").mockResolvedValue(
      info({ mode: "local", token_scope: null }),
    );
    vi.spyOn(mcpApi, "settings").mockResolvedValue(settings());
    render(wrap(<McpSection />));

    expect(await screen.findByTestId("mcp-settings")).toBeInTheDocument();
    expect(mcpApi.settings).toHaveBeenCalledWith("local");
  });
});
