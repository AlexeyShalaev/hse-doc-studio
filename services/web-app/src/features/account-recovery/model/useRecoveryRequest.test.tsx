import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import { LOCAL_BOOTSTRAP, sessionKeys } from "@entities/session";
import { useRecoveryRequest } from "./useRecoveryRequest";

const setup = (code: string) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), LOCAL_BOOTSTRAP);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const call = () => Promise.reject(new ApiError("x", code, 403));
  const hook = renderHook(() => useRecoveryRequest(call), { wrapper });
  return { client, hook };
};

describe("useRecoveryRequest", () => {
  it("csrf_failed обновляет bootstrap: устаревший токен лечится сам", async () => {
    const { client, hook } = setup("csrf_failed");
    await act(async () => {
      await hook.result.current.submit(undefined);
    });
    expect(hook.result.current.failure).toEqual({ code: "csrf_failed" });
    expect(client.getQueryState(sessionKeys.bootstrap())?.isInvalidated).toBe(
      true,
    );
  });

  it("другие отказы bootstrap не трогают", async () => {
    const { client, hook } = setup("token_invalid");
    await act(async () => {
      await hook.result.current.submit(undefined);
    });
    expect(client.getQueryState(sessionKeys.bootstrap())?.isInvalidated).toBe(
      false,
    );
  });
});
