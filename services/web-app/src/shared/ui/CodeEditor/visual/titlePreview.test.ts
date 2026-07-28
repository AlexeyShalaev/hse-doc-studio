import { describe, expect, it } from "vitest";
import { buildTitlePreview } from "./titlePreview";

describe("buildTitlePreview", () => {
  it("builds the two-page ESPD model from resolved document macros", () => {
    const preview = buildTitlePreview(
      "titlePages",
      {
        projectname: "Ядро платформы",
        docname: "Техническое задание",
        doccode: String.raw`RU.01\ ТЗ 01-1`,
        doccodelu: String.raw`RU.01\ ТЗ 01-1-ЛУ`,
        studentname: "А. А. Автор",
        studentgroup: "БПИ-224",
        yearval: "2026",
      },
      "first\nsecond",
    );

    expect(preview.kind).toBe("titlePages");
    if (preview.kind !== "titlePages") return;
    expect(preview.documentCode).toBe("RU.01 ТЗ 01-1");
    expect(preview.approvalCode).toBe("RU.01 ТЗ 01-1-ЛУ");
    expect(preview.executors).toBe("А. А. Автор");
    expect(preview.sourceLineCount).toBe(2);
  });

  it("keeps VКР as one distinct model and omits an empty co-supervisor", () => {
    const preview = buildTitlePreview(
      "vkrTitle",
      {
        hseProjectName: "Удобный редактор",
        hseSpecialization: "Программная инженерия",
        hseAuthorName: "А. А. Автор",
        hseCoSupervisorName: "",
        hseYear: "2026",
      },
      undefined,
    );

    expect(preview.kind).toBe("vkrTitle");
    if (preview.kind !== "vkrTitle") return;
    expect(preview.projectName).toBe("Удобный редактор");
    expect(preview.coSupervisorName).toBeNull();
    expect(preview.sourceLineCount).toBeNull();
  });

  it("renders fill macros as visible placeholders instead of raw TeX", () => {
    const preview = buildTitlePreview(
      "vkrTitle",
      {
        hseProjectName: String.raw`\hseFill{укажите тему}`,
      },
      "",
    );
    expect(preview.projectName).toBe("‹укажите тему›");
  });
});
