import { describe, expect, it, vi } from "vitest";
import {
  EmbeddedInputBlockWidget,
  RequirementsTableInputBlockWidget,
  TitleInputBlockWidget,
} from "./widgets";

describe("source-backed input widgets", () => {
  it("renders ESPD as two distinct pages with resolved project data", () => {
    const dom = new TitleInputBlockWidget(
      "../common/title_template",
      "ЛИСТ УТВЕРЖДЕНИЯ\n\\doccodelu",
      "titlePages",
      {
        projectname: "Ядро облачной платформы",
        docname: "Техническое задание",
        doccode: "RU.01 ТЗ 01-1",
        doccodelu: "RU.01 ТЗ 01-1-ЛУ",
        studentname: "А. А. Автор",
        studentgroup: "БПИ-224",
        yearval: "2026",
      },
    ).toDOM();

    expect(dom.querySelectorAll(".cm-vis-title-page")).toHaveLength(2);
    expect(dom.textContent).toContain("Ядро облачной платформы");
    expect(dom.textContent).toContain("ЛИСТ УТВЕРЖДЕНИЯ");
    expect(dom.textContent).toContain("RU.01 ТЗ 01-1-ЛУ");
  });

  it("renders VКР as exactly one page and opens its own title source", () => {
    const onOpen = vi.fn();
    const dom = new TitleInputBlockWidget(
      "title",
      "\\begin{titlepage} Выпускная квалификационная работа",
      "vkrTitle",
      {
        hseProjectName: "Удобный редактор",
        hseAuthorName: "А. А. Автор",
        hseSpecialization: "Программная инженерия",
      },
      onOpen,
    ).toDOM();

    expect(dom.querySelectorAll(".cm-vis-title-page")).toHaveLength(1);
    expect(dom.textContent).toContain("Выпускная квалификационная работа");
    dom.querySelector<HTMLButtonElement>(".cm-vis-source-open")?.click();
    expect(onOpen).toHaveBeenCalledWith("title");
  });

  it("renders real requirements rows without duplicating the req id", () => {
    const source = String.raw`
      \begin{longtable}{llll}
      \caption{Функциональные требования} \\
      \textbf{№} & \textbf{История} & \textbf{Требование} & \textbf{Область} \\
      \endfirsthead\endhead\endfoot\endlastfoot
      ТЗ-Ф-01 & Как пользователь & \req{ТЗ-Ф-01}{Система должна работать} & Ядро \\
      \end{longtable}
    `;
    const dom = new RequirementsTableInputBlockWidget(
      "requirements_table",
      source,
    ).toDOM();

    expect(dom.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(dom.querySelectorAll("tbody td")).toHaveLength(4);
    expect(dom.querySelector("tbody")?.textContent).toContain(
      "Система должна работать",
    );
    expect(
      dom.querySelector("tbody")?.textContent?.match(/ТЗ-Ф-01/g),
    ).toHaveLength(1);
  });

  it("keeps unknown imported markup inert in the generic preview", () => {
    const dom = new EmbeddedInputBlockWidget(
      "chapter/custom",
      String.raw`\unknown{<img src=x onerror=alert(1)> Безопасный текст}`,
    ).toDOM();

    expect(dom.querySelector("img")).toBeNull();
    expect(dom.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
