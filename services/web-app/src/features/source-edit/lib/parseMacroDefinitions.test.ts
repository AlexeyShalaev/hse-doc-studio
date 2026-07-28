import { describe, expect, it } from "vitest";
import {
  parseMacroDefinitions,
  resolveMacroAliases,
} from "./parseMacroDefinitions";

describe("parseMacroDefinitions", () => {
  it("parses the generated meta.tex style ({%-continuation, comments)", () => {
    const src = [
      "% ── Проект ──",
      "\\newcommand{\\hseProjectName}{%",
      "Ядро облачной платформы}",
      "\\newcommand{\\hseAuthorsCount}{%",
      "1}",
    ].join("\n");
    expect(parseMacroDefinitions(src)).toEqual({
      hseProjectName: "Ядро облачной платформы",
      hseAuthorsCount: "1",
    });
  });

  it("keeps nested braces and macro references verbatim", () => {
    const src =
      "\\newcommand{\\hseLanguages}{\\hseFill{укажите языки}}\n" +
      "\\renewcommand{\\hseGroup}{БПИ{-}229}";
    expect(parseMacroDefinitions(src)).toEqual({
      hseLanguages: "\\hseFill{укажите языки}",
      hseGroup: "БПИ{-}229",
    });
  });

  it("skips definitions with argument specs and unbalanced braces", () => {
    const src =
      "\\newcommand{\\withArg}[1]{arg #1}\n\\newcommand{\\broken}{oops";
    const out = parseMacroDefinitions(src);
    expect(out.withArg).toBe("arg #1");
    expect(out.broken).toBeUndefined();
  });
});

describe("resolveMacroAliases", () => {
  it("resolves \\projectname → \\hseProjectName → value", () => {
    const out = resolveMacroAliases({
      projectname: "\\hseProjectName",
      hseProjectName: "Ядро облачной платформы",
    });
    expect(out.projectname).toBe("Ядро облачной платформы");
  });

  it("leaves references to complex bodies unresolved", () => {
    const out = resolveMacroAliases({
      alias: "\\complex",
      complex: "\\hseFill{заполните}",
    });
    expect(out.alias).toBe("\\complex");
  });
});
