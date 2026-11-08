import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { i18n, useToastStore } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import type { BuildAvailability } from "@entities/runner";
import { buildBlockOf } from "./buildBlock";
import { useCompileStreamStore } from "./compileStreamStore";
import { useStartCompile, useStartCompileAll } from "./useStartCompile";

const SERVER = JSON.parse(
  readFileSync(
    join(
      import.meta.dirname,
      "../../../../../..",
      "contracts/server/fixtures/Bootstrap/server_user.json",
    ),
    "utf8",
  ),
) as Bootstrap;

const P = "P1";
const NONE: BuildAvailability = { cloud: true, any_runner: false, tags: [] };
const TEX_ONLY: BuildAvailability = {
  cloud: true,
  any_runner: true,
  tags: ["tex"],
};
const FULL: BuildAvailability = {
  cloud: true,
  any_runner: true,
  tags: ["office", "tex"],
};
const DOCS = [
  { id: "tz", status: "draft", build_tags: ["tex"] },
  { id: "pres", status: "draft", build_tags: ["office"] },
  { id: "pdf", status: "draft", build_tags: [] },
];

const mockServer = (
  availability: BuildAvailability,
  docs: readonly object[] = DOCS,
) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url.endsWith("/build-availability"))
      return Promise.resolve({ data: availability });
    if (url.endsWith("/documents")) return Promise.resolve({ data: docs });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  const post = vi.spyOn(apiClient, "post");
  return { get, post };
};

const wrapper = (bootstrap: Bootstrap) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  );
  return Wrapper;
};

describe("buildBlockOf", () => {
  it("local mode never blocks", () => {
    expect(
      buildBlockOf({ cloud: false, any_runner: true, tags: [] }, ["tex"]),
    ).toBeNull();
  });

  it("unknown availability does not block", () => {
    expect(buildBlockOf(undefined, ["tex"])).toBeNull();
  });

  it("no runners at all", () => {
    expect(buildBlockOf(NONE, ["tex"])).toEqual({
      reason: "no_runners",
      tags: ["tex"],
    });
  });

  it("runners exist, but none for office", () => {
    expect(buildBlockOf(TEX_ONLY, ["office"])).toEqual({
      reason: "no_runner_for_tags",
      tags: ["office"],
    });
  });

  it("names the cause the server gave for the missing tag", () => {
    expect(
      buildBlockOf({ ...TEX_ONLY, reasons: { office: "personal_paused" } }, [
        "office",
      ]),
    ).toEqual({
      reason: "no_runner_for_tags",
      tags: ["office"],
      cause: "personal_paused",
    });
  });

  it("an unknown cause from a newer server reads as no runner", () => {
    expect(
      buildBlockOf({ ...TEX_ONLY, reasons: { office: "quantum" } }, ["office"])
        ?.cause,
    ).toBe("no_runner");
  });

  it("a document that needs no runner is never blocked", () => {
    expect(buildBlockOf(NONE, [])).toBeNull();
    expect(buildBlockOf(NONE, undefined)).toBeNull();
  });
});

describe("useStartCompile / useStartCompileAll", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    // Поток SSE в jsdom не открыть: запуск потока здесь не проверяем.
    useCompileStreamStore.setState({
      pending: {},
      streams: {},
      start: vi.fn(),
    });
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("server without runners: the build is blocked and nothing is posted", async () => {
    const { post } = mockServer(NONE);
    const { result } = renderHook(() => useStartCompile(P, "tz"), {
      wrapper: wrapper(SERVER),
    });

    await waitFor(() => {
      expect(result.current.block).toEqual({
        reason: "no_runners",
        tags: ["tex"],
      });
    });
    act(() => {
      result.current.start();
    });
    expect(post).not.toHaveBeenCalled();
    expect(useCompileStreamStore.getState().pending).toEqual({});
  });

  it("local mode: no availability request and nothing blocked", async () => {
    const { get } = mockServer(NONE);
    const { result } = renderHook(() => useStartCompile(P, "tz"), {
      wrapper: wrapper(LOCAL_BOOTSTRAP),
    });

    await waitFor(() => {
      expect(get).toHaveBeenCalledWith(`/projects/${P}/documents`);
    });
    expect(result.current.block).toBeNull();
    expect(
      get.mock.calls.some(([url]) => url.endsWith("/build-availability")),
    ).toBe(false);
  });

  it("build all: not blocked while some document needs no runner", async () => {
    const { get } = mockServer(NONE);
    const { result } = renderHook(() => useStartCompileAll(P), {
      wrapper: wrapper(SERVER),
    });

    await waitFor(() => {
      expect(
        get.mock.calls.some(([url]) => url.endsWith("/build-availability")),
      ).toBe(true);
    });
    // Готовый PDF без тегов собирается и без раннера.
    expect(result.current.block).toBeNull();
  });

  it("build all: blocked when no document can be built", async () => {
    mockServer(NONE, DOCS.slice(0, 2));
    const { result } = renderHook(() => useStartCompileAll(P), {
      wrapper: wrapper(SERVER),
    });

    await waitFor(() => {
      expect(result.current.block).toEqual({
        reason: "no_runners",
        tags: ["tex"],
      });
    });
  });

  it("build all: skips documents without a runner and builds the rest", async () => {
    const { get, post } = mockServer(TEX_ONLY);
    post.mockResolvedValue({ data: { compile_id: "c" } });
    const { result } = renderHook(() => useStartCompileAll(P), {
      wrapper: wrapper(SERVER),
    });
    // Ждём, пока подтянется доступность: без неё блокировок ещё нет.
    await waitFor(() => {
      expect(
        get.mock.calls.some(([url]) => url.endsWith("/build-availability")),
      ).toBe(true);
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    act(() => {
      result.current.startAll(["tz", "pres", "pdf"]);
    });

    await waitFor(() => {
      expect(post).toHaveBeenCalledTimes(2);
    });
    const posted = post.mock.calls.map(([url]) => url);
    expect(posted).toEqual([
      `/projects/${P}/documents/tz/compile`,
      `/projects/${P}/documents/pdf/compile`,
    ]);
    expect(useToastStore.getState().toasts).toHaveLength(1);
  });

  it("build all: refused for every document gives one toast and clears 'building'", async () => {
    const { post } = mockServer(FULL);
    post.mockRejectedValue(
      new ApiError("no live runner for tags: tex", "no_runners", 409, {
        tags: ["tex"],
      }),
    );
    const { result } = renderHook(() => useStartCompileAll(P), {
      wrapper: wrapper(SERVER),
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });

    act(() => {
      result.current.startAll(["tz", "pres", "pdf"]);
    });
    expect(Object.keys(useCompileStreamStore.getState().pending)).toHaveLength(
      3,
    );

    await waitFor(() => {
      expect(useCompileStreamStore.getState().pending).toEqual({});
    });
    await waitFor(() => {
      expect(useToastStore.getState().toasts).toHaveLength(1);
    });
    const toasts = useToastStore.getState().toasts;
    expect(toasts[0]?.title).toBe("Облачная сборка сейчас недоступна");
    expect(toasts[0]?.message).toContain("Не поставлены в сборку (3)");
    expect(toasts[0]?.message).toContain("нет раннера для LaTeX-документов");
  });

  it("build all: the office document is refused with a reason, the rest are built and the toast names it", async () => {
    const { post } = mockServer(FULL);
    post.mockImplementation((url: string) =>
      url.includes("/pres/")
        ? Promise.reject(
            new ApiError("Нет раннера в сети…", "no_runner_for_tags", 409, {
              tags: ["office"],
              reason: "personal_paused",
            }),
          )
        : Promise.resolve({ data: { compile_id: "c" } }),
    );
    const { result } = renderHook(() => useStartCompileAll(P), {
      wrapper: wrapper(SERVER),
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });

    act(() => {
      result.current.startAll(["tz", "pres", "pdf"]);
    });

    await waitFor(() => {
      expect(useToastStore.getState().toasts).toHaveLength(1);
    });
    expect(post).toHaveBeenCalledTimes(3);
    const message = useToastStore.getState().toasts[0]?.message ?? "";
    expect(message).toContain("Не поставлены в сборку (1)");
    expect(message).toContain("(личный раннер на паузе)");
    expect(message).toContain("Остальные документы собираются");
    expect(Object.keys(useCompileStreamStore.getState().pending)).toEqual([
      `${P}::tz`,
      `${P}::pdf`,
    ]);
  });

  it("single build refused because the personal runner is paused: the toast says so", async () => {
    const { post } = mockServer(FULL);
    post.mockRejectedValue(
      new ApiError("…", "no_runner_for_tags", 409, {
        tags: ["office"],
        reason: "personal_paused",
      }),
    );
    const { result } = renderHook(() => useStartCompile(P, "pres"), {
      wrapper: wrapper(SERVER),
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });

    act(() => {
      result.current.start();
    });

    await waitFor(() => {
      expect(useToastStore.getState().toasts).toHaveLength(1);
    });
    expect(useToastStore.getState().toasts[0]?.message).toContain(
      "Личный раннер для офисных документов (Word, PowerPoint) на паузе",
    );
  });
});

describe("toast key", () => {
  beforeEach(() => {
    useToastStore.getState().clear();
  });
  afterEach(() => {
    useToastStore.getState().clear();
  });

  it("the same key shows one toast", () => {
    const { push } = useToastStore.getState();
    push({ kind: "error", message: "a", key: "k" });
    push({ kind: "error", message: "a", key: "k" });
    push({ kind: "error", message: "b" });
    expect(useToastStore.getState().toasts).toHaveLength(2);
  });
});
