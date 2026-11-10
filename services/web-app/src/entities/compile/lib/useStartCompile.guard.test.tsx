import { QueryClient } from "@tanstack/react-query";
import {
  act,
  cleanup,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n, useToastStore } from "@shared/lib";
import { sessionKeys, type Bootstrap } from "@entities/session";
import { makeSigningRouteSummary } from "@entities/signing-route/testing";
import { makeGuardHarness } from "@entities/signing-route/testing/guard";
import { useCompileStreamStore } from "./compileStreamStore";
import { useStartCompile, useStartCompileAll } from "./useStartCompile";

// «Собрать», «Пересобрать» и «Собрать всё» у документов на подписании (signing-route.md, 12.7).

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
const DOCS = [
  { id: "tz", status: "ok", build_tags: [] },
  { id: "pres", status: "ok", build_tags: [] },
  { id: "free", status: "ok", build_tags: [] },
];

const setup = () => {
  vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url.endsWith("/build-availability"))
      return Promise.resolve({
        data: { cloud: true, any_runner: true, tags: [] },
      });
    if (url.endsWith("/documents")) return Promise.resolve({ data: DOCS });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  const post = vi
    .spyOn(apiClient, "post")
    .mockResolvedValue({ data: { compile_id: "c" } });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(sessionKeys.bootstrap(), SERVER);
  const harness = makeGuardHarness({
    projectId: P,
    client,
    routes: [makeSigningRouteSummary({ docs: ["tz", "pres"] })],
    docs: [
      { id: "tz", name: "Техническое задание", folder: "tz" },
      { id: "pres", name: "Презентация", folder: "pres" },
      { id: "free", name: "Пояснительная записка", folder: "free" },
    ],
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>{harness.wrapper({ children })}</MemoryRouter>
  );
  return { post, Wrapper };
};

describe("build of a document out for signing", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
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

  it("«Собрать» asks first and builds after continue", async () => {
    const user = userEvent.setup();
    const { post, Wrapper } = setup();
    const { result } = renderHook(() => useStartCompile(P, "tz"), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });

    act(() => {
      result.current.start();
    });
    const dialog = await screen.findByRole("dialog", {
      name: "Документ на подписании",
    });
    expect(dialog).toHaveTextContent(
      "Изменения не попадут в подписываемую версию. Продолжить?",
    );
    expect(post).not.toHaveBeenCalled();
    expect(useCompileStreamStore.getState().pending).toEqual({});

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledTimes(1);
    });
    expect(post.mock.calls[0]?.[0]).toBe(`/projects/${P}/documents/tz/compile`);
  });

  it("cancel builds nothing", async () => {
    const user = userEvent.setup();
    const { post, Wrapper } = setup();
    const { result } = renderHook(() => useStartCompile(P, "pres"), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });
    act(() => {
      result.current.start();
    });
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(post).not.toHaveBeenCalled();
    expect(useCompileStreamStore.getState().pending).toEqual({});
  });

  it("a document not on signing builds at once", async () => {
    const { post, Wrapper } = setup();
    const { result } = renderHook(() => useStartCompile(P, "free"), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });
    act(() => {
      result.current.start();
    });
    // Без вопроса проектная блокировка ставится в тот же такт.
    expect(useCompileStreamStore.getState().pending).not.toEqual({});
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(post).toHaveBeenCalledTimes(1);
    });
  });

  it("«Собрать всё» asks once with the list of affected documents", async () => {
    const user = userEvent.setup();
    const { post, Wrapper } = setup();
    const { result } = renderHook(() => useStartCompileAll(P), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });

    act(() => {
      result.current.startAll(["tz", "pres", "free"]);
    });
    const dialog = await screen.findByRole("dialog", {
      name: "Документы на подписании",
    });
    expect(dialog).toHaveTextContent(
      "Документы на подписании: Техническое задание, Презентация. Изменения не попадут в подписываемые версии. Продолжить?",
    );
    expect(post).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledTimes(3);
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
