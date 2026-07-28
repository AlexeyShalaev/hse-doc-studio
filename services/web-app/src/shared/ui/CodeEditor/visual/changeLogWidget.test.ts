import { describe, expect, it, vi } from "vitest";
import { ChangeLogInputBlockWidget } from "./widgets";

describe("ChangeLogInputBlockWidget", () => {
  it("renders a protected semantic table and opens the shared source", () => {
    const source = String.raw`
      \section*{ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ}
      \begin{tabularx}{\textwidth}{|X|X|}
      \multicolumn{10}{|c|}{Лист регистрации изменений} \\
      Изм. & a & b & c & d & e & f & g & h & i \\
       & & & & & & & & & \\[0.45cm] \hline
      \end{tabularx}
    `;
    const onOpen = vi.fn();
    const dom = new ChangeLogInputBlockWidget(
      "../common/change_log",
      source,
      "RU.01\\ ТЗ 01-1",
      onOpen,
    ).toDOM();

    expect(dom.className).toBe("cm-vis-change-log");
    expect(dom.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(
      dom.querySelector(".cm-vis-change-log-page-header")?.textContent,
    ).toContain("RU.01 ТЗ 01-1");
    expect(dom.querySelector(".cm-vis-change-log-warning")).not.toBeNull();

    const button = dom.querySelector<HTMLButtonElement>(
      ".cm-vis-change-log-open",
    );
    expect(button).not.toBeNull();
    button?.click();
    expect(onOpen).toHaveBeenCalledWith("../common/change_log");
  });
});
