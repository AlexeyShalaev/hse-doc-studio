import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStaleBuildStore } from "./staleBuildStore";
import {
  VERSION_MIN_GAP_MS,
  VERSION_POLL_MS,
  fetchHasNewBuild,
  startVersionWatch,
} from "./versionWatch";

const reply = (body: unknown, type = "application/json"): typeof fetch =>
  vi.fn(() =>
    Promise.resolve(
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        headers: { "content-type": type },
      }),
    ),
  );

describe("fetchHasNewBuild", () => {
  it("более поздняя сборка это новая версия", async () => {
    expect(
      await fetchHasNewBuild(reply({ version: "0.0.0-test", build: "zzzzzz" })),
    ).toBe(true);
  });

  it("та же и более ранняя сборка не считаются новыми (выкатка в процессе)", async () => {
    expect(await fetchHasNewBuild(reply({ build: "test-build" }))).toBe(false);
    expect(await fetchHasNewBuild(reply({ build: "0" }))).toBe(false);
  });

  it("без поля сборки сравнивает версию", async () => {
    expect(await fetchHasNewBuild(reply({ version: "9.9.9" }))).toBe(true);
    expect(await fetchHasNewBuild(reply({ version: "0.0.0-test" }))).toBe(
      false,
    );
  });

  it("index.html вместо JSON, ошибка сервера и сбой сети дают «не знаем»", async () => {
    expect(await fetchHasNewBuild(reply("<html></html>", "text/html"))).toBe(
      false,
    );
    const failing = vi.fn(() =>
      Promise.resolve(new Response("", { status: 500 })),
    );
    expect(await fetchHasNewBuild(failing as unknown as typeof fetch)).toBe(
      false,
    );
    const offline = vi.fn(() => Promise.reject(new TypeError("offline")));
    expect(await fetchHasNewBuild(offline as unknown as typeof fetch)).toBe(
      false,
    );
  });
});

describe("startVersionWatch", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useStaleBuildStore.setState({ reason: null, screenShown: false });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("раз в несколько минут спрашивает версию и показывает баннер", async () => {
    const fetchImpl = reply({ build: "zzzzzz" });
    const stop = startVersionWatch(fetchImpl);
    expect(fetchImpl).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(VERSION_POLL_MS);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(useStaleBuildStore.getState().reason).toBe("version");
    await vi.advanceTimersByTimeAsync(VERSION_POLL_MS);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    stop();
  });

  it("при возврате на вкладку спрашивает не чаще раза в минуту", async () => {
    const fetchImpl = reply({ build: "test-build" });
    const stop = startVersionWatch(fetchImpl);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(fetchImpl).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(VERSION_MIN_GAP_MS);
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    stop();
  });
});
