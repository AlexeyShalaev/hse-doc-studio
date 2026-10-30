import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { MyRunner, MyRunnerToken } from "@entities/runner";
import { MyRunnersSection } from "./ui/MyRunnersSection";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  tokens: vi.fn(),
}));

vi.mock("@entities/runner/api/runnerApi", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "@entities/runner/api/runnerApi",
  );
  return {
    ...actual,
    myRunnersApi: {
      ...(actual.myRunnersApi as object),
      list: api.list,
      tokens: api.tokens,
    },
  };
});

vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useBootstrap: () => ({
    data: { version: "0.3.0", capabilities: { personal_runners: true } },
  }),
}));

const RUNNER: MyRunner = {
  id: "r1",
  name: "personal-e2e",
  state: "online",
  host_kind: "cli",
  tags: ["tex"],
  concurrency: 1,
  ai_concurrency: 0,
  version: "0.3.0",
  created_at: "2026-10-30T10:00:00Z",
  last_seen_at: "2026-10-30T10:00:00Z",
  last_seen_ip: null,
  paused: false,
  revoked: false,
  running_jobs: 0,
  ai_endpoints: [],
  features: [],
};

const TOKEN: MyRunnerToken = {
  id: "t1",
  label: "",
  created_at: "2026-10-30T10:00:00Z",
  expires_at: "2099-10-31T10:00:00Z",
  used: false,
  revoked: false,
};

const renderSection = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <MyRunnersSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("«Мои раннеры»: раздел", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    api.list.mockReset();
    api.tokens.mockReset();
  });
  afterEach(cleanup);

  it("раннер подключился между опросами: после закрытия диалога строка и токены обновляются сразу", async () => {
    api.list.mockResolvedValue([]);
    api.tokens.mockResolvedValue([TOKEN]);
    renderSection();
    expect(await screen.findByTestId("my-runners-empty")).toBeInTheDocument();
    expect(screen.getByTestId("my-runner-token-t1")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("my-runner-connect"));
    expect(screen.getByTestId("runner-connect-dialog")).toBeInTheDocument();
    // Раннер зарегистрировался токеном, пока диалог открыт, но до следующего опроса.
    api.list.mockResolvedValue([RUNNER]);
    api.tokens.mockResolvedValue([]);
    const listCalls = api.list.mock.calls.length;
    const tokenCalls = api.tokens.mock.calls.length;
    await userEvent.keyboard("{Escape}");

    await waitFor(() => {
      expect(api.list.mock.calls.length).toBeGreaterThan(listCalls);
      expect(api.tokens.mock.calls.length).toBeGreaterThan(tokenCalls);
    });
    expect(await screen.findByTestId("my-runner-row-r1")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByTestId("my-runner-token-t1")).toBeNull();
    });
  });
});
