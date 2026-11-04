import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import { installViewport } from "@shared/lib/viewport/testing";
import { Modal } from ".";

type Viewport = ReturnType<typeof installViewport>;

const Harness = ({ onClose = () => undefined }: { onClose?: () => void }) => (
  <Modal
    isOpen
    onClose={onClose}
    title="Share link"
    description="Anyone with the link can read"
    footer={
      <>
        <button type="button" className="btn">
          Cancel
        </button>
        <button type="button" className="btn primary">
          Create
        </button>
      </>
    }
  >
    <input aria-label="Name" />
  </Modal>
);

describe("Modal", () => {
  let viewport: Viewport | undefined;
  afterEach(() => {
    viewport?.restore();
    viewport = undefined;
  });

  it("is a centred dialog on a desktop", () => {
    viewport = installViewport(1360);
    render(<Harness />);
    expect(screen.getByRole("dialog", { name: "Share link" })).toHaveAttribute(
      "data-form",
      "dialog",
    );
  });

  it("is a bottom sheet on a phone, with the same content and a labelled close", () => {
    viewport = installViewport(390);
    render(<Harness />);
    const dialog = screen.getByRole("dialog", { name: "Share link" });
    expect(dialog).toHaveAttribute("data-form", "sheet");
    expect(screen.getByLabelText("Name")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create" })).toBeVisible();
    expect(screen.getByRole("button", { name: /Закрыть|Close/ })).toBeVisible();
  });

  it("closes from the close button on a phone", async () => {
    viewport = installViewport(360);
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /Закрыть|Close/ }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("moves focus into the sheet and keeps Escape working", async () => {
    viewport = installViewport(390);
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(
      true,
    );
    await userEvent.setup().keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
