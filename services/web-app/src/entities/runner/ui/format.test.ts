import { describe, expect, it } from "vitest";
import { diskSize } from "./format";

describe("diskSize", () => {
  it("ноль числом, меньше мегабайта в KB, дальше как в локальном «Диске»", () => {
    expect(diskSize(0)).toBe("0 MB");
    expect(diskSize(100)).toBe("1 KB");
    expect(diskSize(140 * 1024)).toBe("140 KB");
    expect(diskSize(5 * 1024 ** 2)).toBe("5 MB");
    expect(diskSize(3 * 1024 ** 3)).toBe("3.00 GB");
  });
});
