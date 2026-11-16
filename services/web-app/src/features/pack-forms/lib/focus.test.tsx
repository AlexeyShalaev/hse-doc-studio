import { cleanup, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deepestRecord, sectionOfPointer, useRecordFocus } from "./focus";

const Host = ({ at, extra }: { at: string | null; extra?: boolean }) => {
  const ref = useRef<HTMLDivElement>(null);
  useRecordFocus(ref, at, "s");
  return (
    <div ref={ref}>
      <ul>
        <li data-pf-at="/pack_submission/profiles/0" data-testid="profile">
          <ol>
            <li
              data-pf-at="/pack_submission/profiles/0/items/1"
              data-testid="item"
            />
          </ol>
        </li>
        <li data-pf-at="/pack_submission/profiles/1" data-testid="other" />
        {extra && <li data-pf-at="/forms/0" data-testid="late" />}
      </ul>
    </div>
  );
};

const scroll = vi.fn();

describe("форма: переход к записи правила", () => {
  beforeEach(() => {
    scroll.mockClear();
    window.HTMLElement.prototype.scrollIntoView = scroll;
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("раздел формы версии по указателю", () => {
    expect(sectionOfPointer("/meta_fields/nda/supported_kinds")).toBe("fields");
    expect(sectionOfPointer("/forms/0/sections/0/fields/1/visible_if")).toBe(
      "forms",
    );
    expect(sectionOfPointer("/documents/3")).toBe("documents");
    expect(sectionOfPointer("/langs")).toBe("languages");
    expect(sectionOfPointer("/pack_submission/profiles/2/items/0")).toBe(
      "submission",
    );
    expect(sectionOfPointer("/signatures/route")).toBe("submission");
    expect(sectionOfPointer("/checks_version/disabled")).toBe("checks");
    expect(sectionOfPointer("/supported_kinds")).toBeNull();
    expect(sectionOfPointer(null)).toBeNull();
  });

  it("выбирает самую глубокую запись, на которую указывает правило", () => {
    const { container } = render(<Host at={null} />);
    expect(
      deepestRecord(container, "/pack_submission/profiles/0/items/1/when")
        ?.dataset.testid,
    ).toBe("item");
    expect(
      deepestRecord(
        container,
        "/pack_submission/profiles/0/signing_slots/0/when",
      )?.dataset.testid,
    ).toBe("profile");
    // Профиль 10 не «начинается с» профиля 1: совпадение по границе сегмента.
    expect(
      deepestRecord(container, "/pack_submission/profiles/10/items/0"),
    ).toBeNull();
    expect(deepestRecord(container, "/nothing")).toBeNull();
  });

  it("прокручивает, ставит фокус и обводит запись на пару секунд", () => {
    vi.useFakeTimers();
    const { getByTestId } = render(
      <Host at="/pack_submission/profiles/0/items/1/when" />,
    );
    const item = getByTestId("item");
    expect(scroll).toHaveBeenCalled();
    expect(item).toHaveFocus();
    expect(item.dataset.pfFlash).toBe("true");
    vi.advanceTimersByTime(3000);
    expect(item.dataset.pfFlash).toBeUndefined();
  });

  it("запись, появившаяся позже (раздел грузится лениво), находится", async () => {
    const { rerender, findByTestId } = render(
      <Host at="/forms/0/sections/1" />,
    );
    expect(scroll).not.toHaveBeenCalled();
    rerender(<Host at="/forms/0/sections/1" extra />);
    const late = await findByTestId("late");
    await vi.waitFor(() => {
      expect(late).toHaveFocus();
    });
  });

  it("без указателя ничего не происходит", () => {
    render(<Host at={null} />);
    expect(scroll).not.toHaveBeenCalled();
  });
});
