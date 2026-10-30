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
import { ChecksSection } from "./ChecksSection";

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
  const get = vi
    .spyOn(apiClient, "get")
    .mockImplementation(() =>
      Promise.reject(new ApiError("off", "unknown_error", 500)),
    );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <ChecksSection />
      </I18nextProvider>
    </QueryClientProvider>,
  );
  return get;
};

describe("ChecksSection by capabilities", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("server: keeps the per-document hint and never asks for Docker images", () => {
    const get = mount(SERVER);
    expect(
      screen.getByText(i18n.t("settings:checks.perDocumentHint")),
    ).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("local: asks for the LanguageTool images", () => {
    const get = mount(LOCAL_BOOTSTRAP);
    expect(get).toHaveBeenCalled();
  });
});
