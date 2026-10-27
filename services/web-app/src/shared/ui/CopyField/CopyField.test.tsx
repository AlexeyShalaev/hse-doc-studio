import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { CopyField } from ".";

const KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample hse-doc-studio";

describe("CopyField", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows the value read-only under an accessible name", () => {
    render(<CopyField value={KEY} label="Публичный ключ" />);
    const field = screen.getByLabelText("Публичный ключ");
    expect(field).toHaveValue(KEY);
    expect(field).toHaveAttribute("readonly");
    expect(field).toHaveClass("mono");
  });

  it("renders a textarea in multiline mode", () => {
    render(<CopyField value={KEY} label="Ключ" multiline />);
    expect(screen.getByLabelText("Ключ").tagName).toBe("TEXTAREA");
  });

  it("copies the value, announces it and reports the callback", async () => {
    const user = userEvent.setup();
    const onCopied = vi.fn();
    render(<CopyField value={KEY} label="Ключ" onCopied={onCopied} />);
    await user.click(screen.getByRole("button", { name: "Копировать" }));
    expect(await navigator.clipboard.readText()).toBe(KEY);
    expect(onCopied).toHaveBeenCalledTimes(1);
    expect(
      await screen.findByRole("button", { name: "Скопировано" }),
    ).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Скопировано: Ключ");
  });

  it("goes back to the idle state after a moment", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CopyField value={KEY} label="Ключ" />);
    await user.click(screen.getByRole("button", { name: "Копировать" }));
    expect(
      await screen.findByRole("button", { name: "Скопировано" }),
    ).toBeVisible();
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(screen.getByRole("button", { name: "Копировать" })).toBeVisible();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("tells the user to copy by hand when the clipboard is unavailable", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
      new Error("denied"),
    );
    const onCopied = vi.fn();
    render(<CopyField value={KEY} label="Ключ" onCopied={onCopied} />);
    await user.click(screen.getByRole("button", { name: "Копировать" }));
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Не удалось скопировать",
      );
    });
    expect(onCopied).not.toHaveBeenCalled();
  });

  it("speaks English when the interface is English", async () => {
    await i18n.changeLanguage("en");
    render(<CopyField value="abc" label="Fingerprint" />);
    expect(screen.getByRole("button", { name: "Copy" })).toBeVisible();
  });
});
