import { describe, expect, it } from "vitest";
import { buildFigureTemplate } from "./imageInsert";

describe("buildFigureTemplate", () => {
  it("builds a figure with the path, an \\hseFill caption and a slug label", () => {
    const tex = buildFigureTemplate("img/paste-20260717-1201.png");
    expect(tex).toContain(
      "\\includegraphics[width=0.8\\textwidth]{img/paste-20260717-1201.png}",
    );
    expect(tex).toContain("\\caption{\\hseFill{подпись рисунка}}");
    expect(tex).toContain("\\label{fig:paste-20260717-1201}");
    expect(tex.startsWith("\\begin{figure}[h]")).toBe(true);
    expect(tex.endsWith("\\end{figure}")).toBe(true);
  });

  it("slugifies unicode names and never emits an empty label", () => {
    expect(buildFigureTemplate("схема архитектуры.png")).toContain(
      "\\label{fig:img}",
    );
    expect(buildFigureTemplate("img/Схема-V2.png")).toContain(
      "\\label{fig:v2}",
    );
  });
});
