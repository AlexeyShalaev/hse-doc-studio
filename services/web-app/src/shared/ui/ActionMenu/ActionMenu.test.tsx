import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installViewport } from "@shared/lib/viewport/testing";
import { ActionMenu } from "./ActionMenu";

// Шторка на телефоне выезжает снизу, и её пункт может оказаться ровно под пальцем, который
// только что нажал «⋯». Меню открывается по pointerdown, поэтому отпускание и click того же
// жеста долетают уже до пункта. Пункт должен реагировать только на свой жест.

const renderMenu = () => {
  const onIssue = vi.fn();
  const onRevoke = vi.fn();
  render(
    <ActionMenu
      label="Действия с токеном"
      items={[
        { id: "issue", label: "Выпустить новый токен", onSelect: onIssue },
        { id: "revoke", label: "Отозвать", danger: true, onSelect: onRevoke },
      ]}
    />,
  );
  return {
    onIssue,
    onRevoke,
    trigger: screen.getByRole("button", { name: "Действия с токеном" }),
  };
};

describe("ActionMenu as a phone sheet", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  afterEach(() => {
    viewport?.restore();
    viewport = undefined;
  });

  it("ignores the mouse release of the press that opened it", async () => {
    viewport = installViewport(390);
    const user = userEvent.setup();
    const { trigger, onIssue, onRevoke } = renderMenu();
    // Нажали на «⋯», шторка открылась, отпустили уже над пунктом.
    await user.pointer({ keys: "[MouseLeft>]", target: trigger });
    const item = await screen.findByRole("menuitem", {
      name: "Выпустить новый токен",
    });
    expect(item.closest(".adm-menu")).toHaveAttribute("data-form", "sheet");
    await user.pointer({ keys: "[/MouseLeft]", target: item });
    expect(onIssue).not.toHaveBeenCalled();
    expect(onRevoke).not.toHaveBeenCalled();
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("ignores the tap click that lands on an item of the sheet it opened", async () => {
    viewport = installViewport(390);
    const { trigger, onIssue } = renderMenu();
    // Касание: pointerup уходит в «⋯» (неявный захват), а click браузер отдаёт тому, что
    // теперь под пальцем, то есть пункту шторки.
    fireEvent.pointerDown(trigger, { button: 0, pointerType: "touch" });
    const item = await screen.findByRole("menuitem", {
      name: "Выпустить новый токен",
    });
    fireEvent.pointerUp(trigger, { button: 0, pointerType: "touch" });
    fireEvent.click(item, { detail: 1 });
    expect(onIssue).not.toHaveBeenCalled();
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("runs an item tapped with a new gesture after opening", async () => {
    viewport = installViewport(390);
    const user = userEvent.setup();
    const { trigger, onRevoke } = renderMenu();
    await user.click(trigger);
    await user.click(await screen.findByRole("menuitem", { name: "Отозвать" }));
    expect(onRevoke).toHaveBeenCalledOnce();
  });

  it("runs an item chosen from the keyboard after a pointer open", async () => {
    viewport = installViewport(390);
    const user = userEvent.setup();
    const { trigger, onIssue } = renderMenu();
    await user.click(trigger);
    const item = await screen.findByRole("menuitem", {
      name: "Выпустить новый токен",
    });
    act(() => {
      item.focus();
    });
    await user.keyboard("{Enter}");
    expect(onIssue).toHaveBeenCalledOnce();
  });

  it("opens and runs an item from the keyboard alone", async () => {
    viewport = installViewport(390);
    const user = userEvent.setup();
    const { trigger, onRevoke } = renderMenu();
    act(() => {
      trigger.focus();
    });
    await user.keyboard("{Enter}");
    await screen.findByRole("menu");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onRevoke).toHaveBeenCalledOnce();
  });
});

describe("ActionMenu as a desktop dropdown", () => {
  it("keeps press, drag and release: the item under the release runs", async () => {
    const user = userEvent.setup();
    const { trigger, onIssue } = renderMenu();
    await user.pointer({ keys: "[MouseLeft>]", target: trigger });
    const item = await screen.findByRole("menuitem", {
      name: "Выпустить новый токен",
    });
    expect(item.closest(".adm-menu")).toHaveAttribute("data-form", "menu");
    await user.pointer({ keys: "[/MouseLeft]", target: item });
    expect(onIssue).toHaveBeenCalledOnce();
  });
});
