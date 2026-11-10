import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { documentKeys } from "@entities/document";
import type * as DocumentModule from "@entities/document";
import { signatureKeys } from "@entities/signature";
import { signingRouteKeys } from "@entities/signing-route";
import {
  useCompileStreamStore,
  type CompileStreamSlot,
} from "./compileStreamStore";
import { useResumeProjectStreams } from "./useResumeProjectStreams";

vi.mock("@entities/document", async (importOriginal) => ({
  ...(await importOriginal<typeof DocumentModule>()),
  useDocuments: () => ({ data: [] }),
}));

const PROJECT = "p_demo";

const slot = (status: CompileStreamSlot["status"]): CompileStreamSlot => ({
  compileId: "c_1",
  logLines: [],
  status,
  doneInfo: null,
  wait: null,
  placement: null,
  phase: null,
  runStartedAt: null,
  load: null,
  lastEventAt: Date.now(),
  isStalled: false,
});

afterEach(() => {
  useCompileStreamStore.setState({ streams: {}, pending: {}, _closers: {} });
});

describe("сборка закончилась", () => {
  it("перечитывает документы, план подписей и маршруты подписания проекта", () => {
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderHook(
      () => {
        useResumeProjectStreams(PROJECT);
      },
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    act(() => {
      useCompileStreamStore.setState({
        streams: { [`${PROJECT}::doc`]: slot("running") },
      });
    });
    expect(invalidate).not.toHaveBeenCalled();
    act(() => {
      useCompileStreamStore.setState({
        streams: { [`${PROJECT}::doc`]: slot("success") },
      });
    });
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(
      [
        documentKeys.lists(PROJECT),
        signatureKeys.state(PROJECT),
        signingRouteKeys.project(PROJECT),
      ],
    );
  });
});
