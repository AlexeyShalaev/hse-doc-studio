import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Handler = (event: { type: string; data: unknown }) => void;
let emit: Handler = () => undefined;

vi.mock("@shared/lib/sse", () => ({
  createSSEStream: (_url: string, onEvent: Handler) => {
    emit = onEvent;
    return () => undefined;
  },
}));

import { useCompileStreamStore } from "./compileStreamStore";

const slot = () => useCompileStreamStore.getState().streams["p::d"];

describe("compile stream placement", () => {
  beforeEach(() => {
    useCompileStreamStore.getState().clear("p", "d");
    useCompileStreamStore.getState().start("p", "d", "c1");
  });
  afterEach(() => {
    useCompileStreamStore.getState().clear("p", "d");
  });

  it("событие placement меняет место сборки и переживает вывод лога", () => {
    expect(slot()?.placement).toBeNull();
    emit({
      type: "placement",
      data: {
        state: "waiting_personal",
        runner_name: "MacBook Анны",
        runner_owner: "me",
        fallback: null,
        wait_s: 5,
      },
    });
    expect(slot()?.placement?.state).toBe("waiting_personal");
    emit({
      type: "placement",
      data: {
        state: "shared",
        runner_name: null,
        runner_owner: null,
        fallback: "timeout",
        wait_s: 5,
      },
    });
    emit({ type: "log", data: { line: "This is XeTeX" } });
    expect(slot()?.placement?.fallback).toBe("timeout");
  });

  it("непонятное тело снимает место, а не роняет поток", () => {
    emit({ type: "placement", data: { state: "moon" } });
    expect(slot()?.placement).toBeNull();
  });
});
