import { act, cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { useCompileStreamStore } from "@entities/compile";
import { BuildStatusNotice } from "./BuildStatusNotice";
import { DocStateLine } from "./DocStateLine";

type Handler = (event: { type: string; data: unknown }) => void;
const handlers: Record<string, Handler> = {};

vi.mock("@shared/lib/sse", () => ({
  createSSEStream: (url: string, onEvent: Handler) => {
    handlers[url.split("/compiles/")[1]?.split("/")[0] ?? ""] = onEvent;
    return () => undefined;
  },
}));

const T0 = 1_800_000_000_000;
const phase = (name: "queued" | "running", extra: object = {}) => ({
  phase: name,
  queued_at: "2026-11-05T10:00:00Z",
  started_at: name === "running" ? "2026-11-05T10:00:30Z" : null,
  ...extra,
});
const send = (compileId: string, type: string, data: unknown) => {
  act(() => {
    handlers[compileId]?.({ type, data });
  });
};
const tick = (now: number) => {
  vi.spyOn(Date, "now").mockReturnValue(now);
  act(() => {
    useCompileStreamStore.getState().tickWatchdog();
  });
};

const mount = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <BuildStatusNotice projectId="p" isCompiling />
      <DocStateLine projectId="p" docId="a" status="draft" />
      <DocStateLine projectId="p" docId="b" status="draft" />
    </I18nextProvider>,
  );

describe("build status notice and per-document state", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    vi.spyOn(Date, "now").mockReturnValue(T0);
    for (const id of ["a", "b"])
      useCompileStreamStore.getState().clear("p", id);
    useCompileStreamStore.getState().start("p", "a", "ca");
    useCompileStreamStore.getState().start("p", "b", "cb");
  });
  afterEach(() => {
    cleanup();
    for (const id of ["a", "b"])
      useCompileStreamStore.getState().clear("p", id);
    vi.restoreAllMocks();
  });

  it("build-all with concurrency 1: one runs, the rest are queued, nobody is red", () => {
    mount();
    send("ca", "phase", phase("running"));
    send(
      "cb",
      "phase",
      phase("queued", { runners_busy: 1, runners_capacity: 1 }),
    );
    send("cb", "wait", {
      reason: "queued",
      queue_position: 1,
      wait_hint_seconds: null,
      attempt: null,
      max_attempts: null,
    });
    tick(T0 + 4 * 60_000);

    expect(screen.queryByTestId("build-stall-banner")).toBeNull();
    expect(screen.getByTestId("doc-state-b").textContent).toContain(
      "в очереди",
    );
    expect(screen.getByTestId("doc-state-b").textContent).toContain("1 из 1");
    expect(screen.getByTestId("doc-state-b").style.color).not.toContain(
      "--c-err",
    );
    expect(screen.getByTestId("doc-state-a").getAttribute("data-state")).toBe(
      "running",
    );
    expect(screen.getByTestId("build-progress-note").textContent).toContain(
      "в очереди: 1",
    );
  });

  it("a long queue does not redden even after an hour", () => {
    mount();
    send("ca", "phase", phase("queued"));
    send("cb", "phase", phase("queued"));
    tick(T0 + 60 * 60_000);
    expect(screen.queryByTestId("build-stall-banner")).toBeNull();
    expect(screen.getByTestId("build-progress-note").textContent).toContain(
      "Раннер берёт сборки по очереди",
    );
    expect(screen.getByTestId("doc-state-a").style.color).toBe("var(--fg-3)");
  });

  it("a running build that went silent turns red, and a new output line clears it", () => {
    mount();
    send("ca", "phase", phase("running"));
    send("cb", "phase", phase("queued"));
    tick(T0 + 6 * 60_000);

    expect(screen.getByTestId("build-stall-banner").textContent).toContain(
      "мин",
    );
    expect(screen.getByTestId("doc-state-a").style.color).toBe("var(--c-err)");
    expect(screen.getByTestId("doc-state-a").textContent).toContain(
      "не отвечает",
    );
    expect(screen.getByTestId("doc-state-b").style.color).not.toBe(
      "var(--c-err)",
    );

    vi.spyOn(Date, "now").mockReturnValue(T0 + 6 * 60_000 + 1_000);
    send("ca", "log", { line: "Output written" });
    expect(screen.queryByTestId("build-stall-banner")).toBeNull();
    expect(screen.getByTestId("doc-state-a").getAttribute("data-state")).toBe(
      "running",
    );
  });

  it("no suitable runner is its own state, not a stall", () => {
    mount();
    send("ca", "phase", phase("queued"));
    send("cb", "phase", phase("queued"));
    send("ca", "wait", {
      reason: "no_runner",
      queue_position: 1,
      wait_hint_seconds: null,
      attempt: null,
      max_attempts: null,
    });
    tick(T0 + 20 * 60_000);
    expect(screen.getByTestId("doc-state-a").textContent).toBe(
      "нет свободного раннера с нужными тегами",
    );
    expect(screen.queryByTestId("build-stall-banner")).toBeNull();
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    mount();
    send("ca", "phase", phase("queued"));
    expect(screen.getByTestId("doc-state-a").textContent).toBe("queued");
  });

  it("shows finished states for idle documents", () => {
    cleanup();
    render(
      <I18nextProvider i18n={i18n}>
        <DocStateLine projectId="p" docId="z" status="err" />
        <DocStateLine projectId="p" docId="y" status="ok" />
      </I18nextProvider>,
    );
    expect(screen.getByTestId("doc-state-z").textContent).toBe("ошибка");
    expect(screen.getByTestId("doc-state-y").textContent).toBe("собран");
  });
});
