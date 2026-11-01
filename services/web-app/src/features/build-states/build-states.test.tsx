import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { CompileWait } from "@entities/session";
import { CompileWaitNotice, EditorBusyView } from "./index";

const wait = (
  reason: CompileWait["reason"],
  extra: Partial<CompileWait> = {},
): CompileWait => ({
  reason,
  queue_position: null,
  wait_hint_seconds: null,
  attempt: null,
  max_attempts: null,
  ...extra,
});

const mount = (node: React.ReactNode) =>
  render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);

describe("CompileWaitNotice", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("queued: shows the place and the expected wait", () => {
    mount(
      <CompileWaitNotice
        wait={wait("queued", { queue_position: 3, wait_hint_seconds: 45 })}
      />,
    );
    const box = screen.getByTestId("compile-wait-queued");
    expect(box.textContent).toContain("В очереди: 3-й");
    expect(box.textContent).toContain("Ожидание около 45 с");
  });

  it("queued: rounds a long wait up to minutes", () => {
    mount(
      <CompileWaitNotice
        wait={wait("queued", { queue_position: 9, wait_hint_seconds: 130 })}
      />,
    );
    expect(screen.getByTestId("compile-wait-queued").textContent).toContain(
      "около 3 мин",
    );
  });

  it("queued without a place still reads well", () => {
    mount(<CompileWaitNotice wait={wait("queued")} />);
    const text = screen.getByTestId("compile-wait-queued").textContent;
    expect(text).toContain("В очереди");
    expect(text).not.toContain("null");
  });

  it("quota_wait: explains the per-user limit", () => {
    mount(
      <CompileWaitNotice wait={wait("quota_wait", { queue_position: 1 })} />,
    );
    expect(screen.getByTestId("compile-wait-quota_wait").textContent).toContain(
      "Ждём вашей очереди: 1-й",
    );
  });

  it("no_runner: tells to contact the administrator, no retry while waiting", () => {
    mount(<CompileWaitNotice wait={wait("no_runner")} onRetry={vi.fn()} />);
    const box = screen.getByTestId("compile-wait-no_runner");
    expect(box.textContent).toContain("Нет доступных раннеров");
    expect(box.textContent).toContain("Обратитесь к администратору");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("no_runner finished: offers a retry", async () => {
    const onRetry = vi.fn();
    mount(
      <CompileWaitNotice wait={wait("no_runner")} finished onRetry={onRetry} />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Повторить сборку" }),
    );
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("runner_lost: shows the attempt counter", () => {
    mount(
      <CompileWaitNotice
        wait={wait("runner_lost", { attempt: 2, max_attempts: 3 })}
      />,
    );
    expect(
      screen.getByTestId("compile-wait-runner_lost").textContent,
    ).toContain("Раннер потерян, повторяем (2/3)");
  });

  it("superseded: explains and rebuilds", async () => {
    const onRetry = vi.fn();
    mount(
      <CompileWaitNotice
        wait={wait("superseded")}
        finished
        onRetry={onRetry}
      />,
    );
    expect(screen.getByTestId("compile-wait-superseded").textContent).toContain(
      "Сборка заменена более новой",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Собрать заново" }),
    );
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders in English", async () => {
    await i18n.changeLanguage("en");
    mount(
      <CompileWaitNotice
        wait={wait("queued", { queue_position: 2, wait_hint_seconds: 20 })}
      />,
    );
    const text = screen.getByTestId("compile-wait-queued").textContent;
    expect(text).toContain("Queued: #2");
    expect(text).toContain("Expected wait about 20 s");
  });
});

describe("EditorBusyView", () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("counts down, then allows a retry", () => {
    const onRetry = vi.fn();
    mount(
      <EditorBusyView
        retryAfterSeconds={2}
        limit={18}
        onRetry={onRetry}
        downloadHref="/f/report.docx"
      />,
    );
    const retry = screen.getByRole("button");
    expect(retry.textContent).toContain("Повторить через 2 с");
    expect((retry as HTMLButtonElement).disabled).toBe(true);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    const ready = screen.getByRole("button", { name: "Повторить" });
    expect((ready as HTMLButtonElement).disabled).toBe(false);
    ready.click();
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("offers the file download and states the limit", () => {
    mount(
      <EditorBusyView
        retryAfterSeconds={30}
        limit={18}
        onRetry={vi.fn()}
        downloadHref="/f/report.docx"
      />,
    );
    const link = screen.getByRole("link", { name: /Скачать файл/ });
    expect(link.getAttribute("href")).toBe("/f/report.docx");
    expect(screen.getByTestId("editor-busy").textContent).toContain("до 18");
  });

  it("hides the download when the file is unknown", () => {
    mount(
      <EditorBusyView
        retryAfterSeconds={30}
        limit={18}
        onRetry={vi.fn()}
        downloadHref={null}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });
});
