import { describe, expect, it } from "vitest";
import { isCheckStale, UPDATE_CHECK_TTL_MS } from "./isCheckStale";

const NOW = Date.parse("2026-07-26T12:00:00Z");

describe("isCheckStale", () => {
  it("treats a never-checked install as stale", () => {
    expect(isCheckStale(null, NOW)).toBe(true);
    expect(isCheckStale(undefined, NOW)).toBe(true);
    expect(isCheckStale("", NOW)).toBe(true);
  });

  it("treats an unparsable timestamp as stale", () => {
    // Лучше один лишний запрос, чем молчание из-за мусора в кэше.
    expect(isCheckStale("not a date", NOW)).toBe(true);
  });

  it("keeps a recent check fresh", () => {
    const recent = new Date(NOW - UPDATE_CHECK_TTL_MS / 2).toISOString();

    expect(isCheckStale(recent, NOW)).toBe(false);
  });

  it("goes stale once the TTL has elapsed", () => {
    const old = new Date(NOW - UPDATE_CHECK_TTL_MS).toISOString();

    expect(isCheckStale(old, NOW)).toBe(true);
  });

  it("tolerates a timestamp from the future without re-checking", () => {
    // Часы контейнера могут уехать вперёд относительно браузера; отрицательная
    // разница не должна читаться как «пора проверять».
    const future = new Date(NOW + 60_000).toISOString();

    expect(isCheckStale(future, NOW)).toBe(false);
  });
});
