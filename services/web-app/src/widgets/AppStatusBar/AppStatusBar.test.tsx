import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";

vi.mock("@entities/system", () => ({
  useRunnerHealth: () => ({ data: undefined, isError: false }),
}));
vi.mock("@entities/app-settings", () => ({
  useAppSettings: () => ({ data: { default_engine: "xelatex" } }),
}));
vi.mock("@features/git-sync", () => ({ SyncStatusSegment: () => null }));
vi.mock("@features/template-update", () => ({
  useTemplateUpdateSignal: () => ({
    currentVersion: "",
    update: null,
    markers: [],
  }),
}));

import { AppStatusBar } from "./AppStatusBar";

const mount = (bootstrap: Bootstrap) => {
  const client = new QueryClient();
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AppStatusBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("AppStatusBar", () => {
  afterEach(cleanup);

  it("локально показывает docker и движок", () => {
    mount(LOCAL_BOOTSTRAP);
    expect(screen.getByText(/docker ·/)).toBeVisible();
    expect(screen.getByText("xelatex")).toBeVisible();
  });

  it("на сервере без docker_ui и local_services_ui их нет", () => {
    mount({
      ...LOCAL_BOOTSTRAP,
      mode: "server",
      capabilities: {
        ...LOCAL_BOOTSTRAP.capabilities,
        docker_ui: false,
        local_services_ui: false,
      },
    });
    expect(screen.queryByText(/docker ·/)).toBeNull();
    expect(screen.queryByText("xelatex")).toBeNull();
  });
});
