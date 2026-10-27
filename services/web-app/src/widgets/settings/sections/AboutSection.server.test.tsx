import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { i18n } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { AboutSection } from "./AboutSection";

const SERVER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  capabilities: {
    ...LOCAL_BOOTSTRAP.capabilities,
    docker_ui: false,
    self_update: false,
    local_services_ui: false,
  },
};

const mount = (bootstrap: Bootstrap) => {
  const calls: string[] = [];
  vi.spyOn(apiClient, "get").mockImplementation((url) => {
    calls.push(url);
    return Promise.reject(new ApiError("off", "unknown_error", 500));
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <AboutSection />
      </I18nextProvider>
    </QueryClientProvider>,
  );
  return calls;
};

describe("AboutSection by capabilities", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("server: no update controls and no update or settings requests", () => {
    const calls = mount(SERVER);
    expect(screen.queryByText("Обновления")).not.toBeInTheDocument();
    expect(document.getElementById("about-updates")).toBeNull();
    expect(document.getElementById("about-auto-update")).toBeNull();
    expect(document.getElementById("about-version-switch")).toBeNull();
    expect(document.getElementById("about-data-dir")).toBeNull();
    expect(calls.every((url) => url === "/system/info")).toBe(true);
  });

  it("local: the update rows are shown", () => {
    mount(LOCAL_BOOTSTRAP);
    expect(document.getElementById("about-updates")).not.toBeNull();
    expect(document.getElementById("about-version-switch")).not.toBeNull();
  });
});
