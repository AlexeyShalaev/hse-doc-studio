import { describe, expect, it } from "vitest";
import {
  bundleStem,
  isEncryptedBundleName,
  suggestedProjectName,
} from "./cloneNames";

describe("имена при клонировании", () => {
  it("зашифрованный файл узнаётся по расширению", () => {
    expect(isEncryptedBundleName("paper.bundle.hseenc")).toBe(true);
    expect(isEncryptedBundleName("PAPER.HSEENC")).toBe(true);
    expect(isEncryptedBundleName("paper.bundle")).toBe(false);
  });

  it("имя файла без расширения и метки времени выгрузки", () => {
    expect(bundleStem("course-paper-20261026-0930.bundle")).toBe(
      "course-paper",
    );
    expect(bundleStem("course-paper-20261026-0930.bundle.hseenc")).toBe(
      "course-paper",
    );
    expect(bundleStem("paper.bundle")).toBe("paper");
    expect(bundleStem("архив.zip")).toBe("архив.zip");
  });

  it("название берётся из проекта, потом из файла, потом из адреса", () => {
    expect(
      suggestedProjectName({
        projectName: " Курсовая ",
        repo: "paper",
        fileName: "x.bundle",
      }),
    ).toBe("Курсовая");
    expect(
      suggestedProjectName({
        projectName: null,
        repo: "paper",
        fileName: "my-20261026-0930.bundle",
      }),
    ).toBe("my");
    expect(
      suggestedProjectName({
        projectName: null,
        repo: "paper.git",
        fileName: null,
      }),
    ).toBe("paper");
    expect(
      suggestedProjectName({ projectName: null, repo: null, fileName: null }),
    ).toBe("");
  });
});
