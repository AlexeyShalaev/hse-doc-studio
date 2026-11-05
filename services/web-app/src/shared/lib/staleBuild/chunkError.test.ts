import { describe, expect, it } from "vitest";
import { isChunkLoadError } from "./chunkError";

describe("isChunkLoadError", () => {
  it.each([
    "Failed to fetch dynamically imported module: https://x.ru/assets/admin-BnUkldQj.js",
    "error loading dynamically imported module: /assets/a.js",
    "Importing a module script failed.",
    "Unable to preload CSS for /assets/admin-1.css",
    "Loading chunk 12 failed.",
  ])("узнаёт сообщение: %s", (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true);
    expect(isChunkLoadError(message)).toBe(true);
    expect(isChunkLoadError({ message })).toBe(true);
  });

  it("узнаёт ChunkLoadError по имени", () => {
    const error = new Error("boom");
    error.name = "ChunkLoadError";
    expect(isChunkLoadError(error)).toBe(true);
  });

  it("обычные ошибки не считает устаревшей сборкой", () => {
    expect(isChunkLoadError(new Error("Network Error"))).toBe(false);
    expect(isChunkLoadError(new TypeError("x is undefined"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
    expect(isChunkLoadError(undefined)).toBe(false);
    expect(isChunkLoadError({ status: 500 })).toBe(false);
  });
});
