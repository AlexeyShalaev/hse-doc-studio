import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { notifyPackFilesSaved, usePackFilesRevision } from "./filesRevision";

describe("счётчик записей файлов пространства", () => {
  it("растёт у подписанных на своё пространство, чужое не трогает", () => {
    const mine = renderHook(() => usePackFilesRevision("ws-files-a"));
    const other = renderHook(() => usePackFilesRevision("ws-files-b"));
    const start = mine.result.current;
    act(() => {
      notifyPackFilesSaved("ws-files-a");
      notifyPackFilesSaved("ws-files-a");
    });
    expect(mine.result.current).toBe(start + 2);
    expect(other.result.current).toBe(0);
  });
});
