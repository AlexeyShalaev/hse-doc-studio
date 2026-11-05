import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@shared/lib/sse", () => ({
  createSSEStream: () => () => undefined,
}));

import { useCompileStreamStore } from "./compileStreamStore";

const PROJECT = "p1";
const DOC = "topic_application";
const KEY = `${PROJECT}::${DOC}`;

describe("settleFromServer", () => {
  beforeEach(() => {
    useCompileStreamStore.setState({ streams: {}, pending: {}, _closers: {} });
  });

  it("закрывает слот «идёт» своей сборки и снимает признак зависания", () => {
    useCompileStreamStore.getState().start(PROJECT, DOC, "c1");
    useCompileStreamStore.setState((s) => {
      const slot = s.streams[KEY];
      if (!slot) throw new Error("slot is missing");
      return { streams: { ...s.streams, [KEY]: { ...slot, isStalled: true } } };
    });

    useCompileStreamStore
      .getState()
      .settleFromServer(PROJECT, DOC, "c1", "failure");

    const slot = useCompileStreamStore.getState().streams[KEY];
    expect(slot?.status).toBe("failure");
    expect(slot?.isStalled).toBe(false);
  });

  it("не трогает слот более новой сборки того же документа", () => {
    useCompileStreamStore.getState().start(PROJECT, DOC, "c2");

    useCompileStreamStore
      .getState()
      .settleFromServer(PROJECT, DOC, "c1", "failure");

    expect(useCompileStreamStore.getState().streams[KEY]?.status).toBe(
      "running",
    );
  });
});
