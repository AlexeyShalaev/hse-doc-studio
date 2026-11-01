import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { AdminChunkError } from "./AdminChunkError";
import { AdminChunkLoading } from "./AdminChunkLoading";

afterEach(cleanup);

describe("состояния загрузки чанка админки", () => {
  it("ошибка показывает сообщение и повтор вызывает обработчик", async () => {
    const onRetry = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <AdminChunkError onRetry={onRetry} />
      </I18nextProvider>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    await userEvent.click(screen.getByTestId("admin-chunk-retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("ожидание даёт одну подпись «Загрузка» без жёсткой английской", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AdminChunkLoading size="lg" />
      </I18nextProvider>,
    );
    const status = screen.getAllByRole("status");
    expect(status).toHaveLength(1);
    expect(status[0]?.getAttribute("aria-label")).not.toBe("admin");
  });
});
