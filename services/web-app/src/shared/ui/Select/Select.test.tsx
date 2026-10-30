import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { Select } from "./Select";

// Затемнение модального окна (.scrim) лежит на слое 100, его панель на 102.
const MODAL_PANEL_LAYER = 102;

describe("Select", () => {
  beforeAll(() => {
    // Radix Select ловит указатель; в jsdom этих методов нет.
    const proto = Element.prototype as Partial<Element> & {
      hasPointerCapture?: (id: number) => boolean;
      releasePointerCapture?: (id: number) => void;
      scrollIntoView?: () => void;
    };
    proto.hasPointerCapture ??= () => false;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
  });
  afterEach(cleanup);

  it("список открывается над модальным окном: щелчок по пункту не попадает в затемнение", async () => {
    render(
      <Select
        ariaLabel="Раннер"
        options={[{ value: "r1", label: "personal-e2e" }]}
      />,
    );
    await userEvent.click(screen.getByRole("combobox", { name: "Раннер" }));
    const listbox = await screen.findByRole("listbox");
    expect(Number(listbox.style.zIndex)).toBeGreaterThan(MODAL_PANEL_LAYER);
  });
});
