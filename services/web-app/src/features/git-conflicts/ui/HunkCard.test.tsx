import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import type { HunkSegment } from "../model/conflictModel";
import { HunkCard } from "./HunkCard";

afterEach(cleanup);

const hunk = (ours: string[], theirs: string[]): HunkSegment => ({
  type: "hunk",
  key: "h-1",
  ours,
  base: ours.length === 0 ? [] : ["Исходная."],
  theirs,
  ours_start: 4,
  result_start: 4,
});

const renderCard = (segment: HunkSegment) =>
  render(
    <HunkCard
      hunk={segment}
      index={0}
      total={1}
      choice={undefined}
      theirsLabel="Анна"
      onChoose={vi.fn()}
      onClear={vi.fn()}
      onActivate={vi.fn()}
    />,
  );

describe("HunkCard", () => {
  it.each([
    ["mine", [], ["Строка их."]],
    ["theirs", ["Строка моя."], []],
  ] as const)(
    "shows a placeholder, not a blank line, for an empty %s side",
    (empty, ours, theirs) => {
      const { container } = renderCard(hunk([...ours], [...theirs]));
      const column = container.querySelector(`[data-side="${empty}"]`);
      expect(column).not.toBeNull();
      const lines = within(column as HTMLElement).queryAllByText(/./, {
        selector: ".hunk-code",
      });
      expect(lines).toHaveLength(1);
      expect(
        (column as HTMLElement).querySelectorAll("[data-own]"),
      ).toHaveLength(0);
      const other = container.querySelector(
        `[data-side="${empty === "mine" ? "theirs" : "mine"}"]`,
      );
      expect(
        (other as HTMLElement).querySelectorAll("[data-own='true']"),
      ).toHaveLength(1);
      expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
    },
  );
});
