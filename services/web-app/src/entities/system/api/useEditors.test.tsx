import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { systemApi } from "./systemApi";
import { useEditors } from "./systemQueries";

const run = (bootstrap: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useEditors(), { wrapper });
};

describe("useEditors", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("на сервере без open_in_editor редакторы хоста не запрашиваются", () => {
    const spy = vi
      .spyOn(systemApi, "getEditors")
      .mockResolvedValue({ os: "linux", editors: [] });
    run({
      ...LOCAL_BOOTSTRAP,
      mode: "server",
      capabilities: { ...LOCAL_BOOTSTRAP.capabilities, open_in_editor: false },
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it("в локальном режиме список запрашивается", async () => {
    const spy = vi
      .spyOn(systemApi, "getEditors")
      .mockResolvedValue({ os: "linux", editors: [] });
    run(LOCAL_BOOTSTRAP);
    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
  });
});
