import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { ProvidersSection } from "./ProvidersSection";

const SERVER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  capabilities: { ...LOCAL_BOOTSTRAP.capabilities, local_services_ui: false },
};

const OWN_PROVIDER = {
  id: "p1",
  name: "Anthropic",
  type: "claude",
  base_url: "",
  models: ["claude-sonnet-4-5"],
  has_api_key: true,
  created_at: "2026-10-01T00:00:00Z",
  ssl_verify: true,
  connect_timeout_s: 10,
  request_timeout_s: 60,
  // Локальный бэкенд тоже присылает источник у каждого провайдера.
  source: "own",
};

const mockGet = (providers: unknown[] = []) => {
  const calls: string[] = [];
  vi.spyOn(apiClient, "get").mockImplementation((url) => {
    calls.push(url);
    const data = url === "/ai-providers" ? providers : {};
    return Promise.resolve({ data, config: { url } });
  });
  return calls;
};

const mount = (bootstrap: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <ProvidersSection />
    </QueryClientProvider>,
  );
};

describe("ProvidersSection: локальный рантайм", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("server: не спрашивает статус локальной Ollama и не говорит про локальное хранение ключей", async () => {
    const calls = mockGet();
    mount(SERVER);
    await waitFor(() => {
      expect(calls).toContain("/ai-providers");
    });
    expect(calls).not.toContain("/ai-runtime/status");
    expect(screen.getByText(/stored encrypted on the server/)).toBeTruthy();
    expect(screen.queryByText(/stored locally/)).toBeNull();
  });

  it("local: статус рантайма запрашивается", async () => {
    const calls = mockGet();
    mount(LOCAL_BOOTSTRAP);
    await waitFor(() => {
      expect(calls).toContain("/ai-runtime/status");
    });
  });

  it("local: source: own не добавляет метку источника и строку порядка", async () => {
    mockGet([OWN_PROVIDER]);
    mount(LOCAL_BOOTSTRAP);
    expect((await screen.findAllByText("Anthropic")).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("ai-provider-source-p1")).toBeNull();
    expect(screen.queryByText(/yours, then the organization/)).toBeNull();
  });

  it("server: метка источника и порядок по умолчанию", async () => {
    mockGet([OWN_PROVIDER]);
    mount(SERVER);
    expect(await screen.findByTestId("ai-provider-source-p1")).toHaveAttribute(
      "data-source",
      "own",
    );
  });
});
