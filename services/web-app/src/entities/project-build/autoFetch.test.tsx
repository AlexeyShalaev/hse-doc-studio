import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAutoFetchCloudBuilds } from ".";

const api = vi.hoisted(() => ({ fetch: vi.fn() }));

vi.mock("./api/buildApi", () => ({
  cloudBuildsApi: { list: vi.fn() },
  localBuildsApi: { list: vi.fn(), fetch: api.fetch },
}));

describe("автополучение облачных сборок", () => {
  it("идёт с auto=true по всем документам и обновляет статус сборок", async () => {
    api.fetch.mockResolvedValue({ items: [] });
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useAutoFetchCloudBuilds(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    await result.current("p1");
    expect(api.fetch).toHaveBeenCalledWith("p1", {
      doc_id: null,
      force: false,
      auto: true,
    });
    expect(invalidate).toHaveBeenCalled();
  });
});
