import { describe, expect, it } from "vitest";
import { PRE_LAUNCH_CODES, hasBuildOutput, shortReason } from "./failureText";

describe("shortReason", () => {
  it("takes the first sentence", () => {
    expect(
      shortReason("Docker недоступен. Запустите Docker Desktop и повторите."),
    ).toBe("Docker недоступен.");
  });

  it("keeps a text without a full stop whole", () => {
    expect(shortReason("  Причина не определена  ")).toBe(
      "Причина не определена",
    );
  });

  it("does not cut inside a file name or a version", () => {
    expect(shortReason("Нет образа texlive/texlive:latest. Установите.")).toBe(
      "Нет образа texlive/texlive:latest.",
    );
  });
});

describe("hasBuildOutput", () => {
  it("is false for an empty log and for service lines only", () => {
    expect(hasBuildOutput([])).toBe(false);
    expect(hasBuildOutput(["", "[runner] image_missing: x"])).toBe(false);
    expect(hasBuildOutput(["[error] image_missing: text"])).toBe(false);
  });

  it("is true once a build line is present", () => {
    expect(hasBuildOutput(["This is XeTeX", "[error] build_failed: x"])).toBe(
      true,
    );
  });
});

describe("PRE_LAUNCH_CODES", () => {
  it("knows the environment refusals", () => {
    for (const code of ["image_missing", "docker_unavailable", "no_runners"]) {
      expect(PRE_LAUNCH_CODES.has(code)).toBe(true);
    }
    expect(PRE_LAUNCH_CODES.has("build_failed")).toBe(false);
  });
});
