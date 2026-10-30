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

const mockGet = () => {
  const calls: string[] = [];
  vi.spyOn(apiClient, "get").mockImplementation((url) => {
    calls.push(url);
    const data = url === "/ai-providers" ? [] : {};
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
});
