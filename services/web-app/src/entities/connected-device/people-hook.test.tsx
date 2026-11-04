import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MIN_SIGNAL_GAP_MS, PLACE_DEBOUNCE_MS } from "./lib/peopleLib";
import { useProjectPeople, type Place } from "./api/peopleQueries";
import { makePeople, makePerson } from "./testing";

const api = vi.hoisted(() => ({ signal: vi.fn(), leave: vi.fn() }));
vi.mock("./api/peopleApi", () => ({
  peopleApi: { signal: api.signal, leave: api.leave },
}));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    {children}
  </QueryClientProvider>
);

const tick = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

const view = (initial: Place) =>
  renderHook(({ place }: { place: Place }) => useProjectPeople("p1", place), {
    wrapper,
    initialProps: { place: initial },
  });

const viewing: Place = { activity: "viewing", docId: "a" };

beforeEach(() => {
  vi.useFakeTimers();
  api.signal.mockResolvedValue(makePeople([makePerson({ me: true })]));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("сигнал вкладки", () => {
  it("при открытии уходит один сигнал, дальше раз в интервал сервера", async () => {
    view(viewing);
    await tick(10);
    expect(api.signal).toHaveBeenCalledTimes(1);

    await tick(59_000);
    expect(api.signal).toHaveBeenCalledTimes(1);
    await tick(2_000);
    expect(api.signal).toHaveBeenCalledTimes(2);
  });

  it("смена места не шлёт сигнал сразу: ждёт паузу и общий минимальный промежуток", async () => {
    const { rerender } = view(viewing);
    await tick(10);
    rerender({ place: { activity: "editing", docId: "a" } });
    await tick(PLACE_DEBOUNCE_MS + 100);
    expect(api.signal).toHaveBeenCalledTimes(1);

    await tick(MIN_SIGNAL_GAP_MS);
    expect(api.signal).toHaveBeenCalledTimes(2);
    expect(api.signal.mock.calls[1]?.[1]).toMatchObject({
      activity: "editing",
      doc_id: "a",
    });
  });

  it("быстрое перелистывание вкладок даёт один сигнал с последним местом", async () => {
    const { rerender } = view(viewing);
    await tick(10);
    for (const activity of ["reviewing", "building", "editing"] as const) {
      rerender({ place: { activity, docId: "a" } });
      await tick(300);
    }
    await tick(MIN_SIGNAL_GAP_MS + PLACE_DEBOUNCE_MS);
    expect(api.signal).toHaveBeenCalledTimes(2);
    expect(api.signal.mock.calls[1]?.[1]).toMatchObject({
      activity: "editing",
    });
  });

  it("то же место сигнала не требует", async () => {
    const { rerender } = view(viewing);
    await tick(10);
    rerender({ place: { activity: "viewing", docId: "a" } });
    await tick(MIN_SIGNAL_GAP_MS * 2);
    expect(api.signal).toHaveBeenCalledTimes(1);
  });

  it("закрытие вкладки и уход со страницы убирают сессию", async () => {
    const { unmount } = view(viewing);
    await tick(10);
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    expect(api.leave).toHaveBeenCalledTimes(1);
    unmount();
    expect(api.leave).toHaveBeenCalledTimes(2);
    expect(api.leave).toHaveBeenLastCalledWith("p1", expect.any(String));
  });
});
