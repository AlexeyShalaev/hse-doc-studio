import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import type { AutoSyncInfo } from "../model/useAutoSync";
import { AutoSyncRow } from "./AutoSyncRow";

const NOW = Date.parse("2026-11-02T10:30:00Z");

const info = (patch: Partial<AutoSyncInfo> = {}): AutoSyncInfo => ({
  available: true,
  enabled: true,
  explicit: false,
  phase: "watching",
  stop: null,
  failures: 0,
  isSaving: false,
  setEnabled: vi.fn(),
  ...patch,
});

describe("AutoSyncRow", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("shows the switch state and what auto sync is doing", () => {
    render(<AutoSyncRow auto={info({ phase: "waiting" })} now={NOW} />);

    expect(
      screen.getByRole("switch", { name: "Синхронизировать автоматически" }),
    ).toHaveProperty("ariaChecked", "true");
    expect(
      screen.getByText("Синхронизирую после паузы в правках"),
    ).toBeTruthy();
  });

  it("names the reason when auto sync has stopped", () => {
    render(
      <AutoSyncRow
        auto={info({ phase: "stopped", stop: "conflicts" })}
        now={NOW}
      />,
    );

    expect(
      screen.getByText("Остановлена: нужно разобрать конфликты"),
    ).toBeTruthy();
  });

  it("turns auto sync off and on from the switch", async () => {
    const setEnabled = vi.fn();
    const { rerender } = render(
      <AutoSyncRow auto={info({ setEnabled })} now={NOW} />,
    );

    await userEvent.click(screen.getByRole("switch"));
    expect(setEnabled).toHaveBeenLastCalledWith(false);

    rerender(
      <AutoSyncRow
        auto={info({ enabled: false, phase: "off", setEnabled })}
        now={NOW}
      />,
    );
    expect(screen.getByText("Выключена: синхронизируй вручную")).toBeTruthy();
    await userEvent.click(screen.getByRole("switch"));
    expect(setEnabled).toHaveBeenLastCalledWith(true);
  });

  it("locks the switch while the choice is being saved", () => {
    render(<AutoSyncRow auto={info({ isSaving: true })} now={NOW} />);

    expect(screen.getByRole("switch")).toHaveProperty("disabled", true);
  });

  it("reports the last PDF upload, success and failure", () => {
    const { rerender } = render(
      <AutoSyncRow
        auto={info()}
        now={NOW}
        pdf={{
          last: {
            docId: "coursework",
            at: "2026-11-02T10:25:00Z",
            ok: true,
            error: null,
            message: null,
          },
        }}
      />,
    );
    expect(screen.getByTestId("pdf-upload-line").textContent).toContain(
      "coursework: выгружен",
    );

    rerender(
      <AutoSyncRow
        auto={info()}
        now={NOW}
        pdf={{
          last: {
            docId: "coursework",
            at: "2026-11-02T10:25:00Z",
            ok: false,
            error: "pdf_forbidden",
            message: "Выгружать PDF может редактор",
          },
        }}
      />,
    );
    expect(screen.getByTestId("pdf-upload-line").textContent).toBe(
      "coursework: не выгружен (Выгружать PDF может редактор)",
    );
  });

  it("says nothing about PDFs for a project that does not upload them", () => {
    render(<AutoSyncRow auto={info()} now={NOW} pdf={null} />);

    expect(screen.queryByTestId("pdf-upload-line")).toBeNull();
  });
});
