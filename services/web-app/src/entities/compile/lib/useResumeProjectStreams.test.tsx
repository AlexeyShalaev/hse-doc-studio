import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { documentKeys } from "@entities/document";
import type * as DocumentModule from "@entities/document";
import { signatureKeys } from "@entities/signature";
import { signingRouteKeys } from "@entities/signing-route";
import { toast } from "@shared/lib";
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

  it("места подписей из шаблона подвинуты по новой вёрстке: тост с числом", () => {
    const info = vi.spyOn(toast, "info").mockReturnValue("t");
    const client = new QueryClient();
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
    act(() => {
      useCompileStreamStore.setState({
        streams: {
          [`${PROJECT}::doc`]: {
            ...slot("success"),
            doneInfo: {
              status: "success",
              pages: 1,
              warnings: 0,
              errors: 0,
              signature_places_moved: 2,
            },
          },
        },
      });
    });
    expect(info).toHaveBeenCalledWith(
      "Места подписей из шаблона подвинуты по новой вёрстке: 2",
    );
    info.mockRestore();
  });

  it("без сдвинутых мест тоста нет", () => {
    const info = vi.spyOn(toast, "info").mockReturnValue("t");
    const client = new QueryClient();
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
    act(() => {
      useCompileStreamStore.setState({
        streams: { [`${PROJECT}::doc`]: slot("success") },
      });
    });
    expect(info).not.toHaveBeenCalled();
    info.mockRestore();
  });
});
