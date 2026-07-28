import { describe, expect, it } from "vitest";
import {
  baseName,
  isAbsoluteHostPath,
  joinPath,
  parentPath,
  toCrumbs,
} from "./hostPath";

describe("toCrumbs", () => {
  it("keeps the drive letter as a navigable root on windows", () => {
    expect(toCrumbs("C:/Users/Иван/HSE")).toEqual([
      { label: "C:/", path: "C:/" },
      { label: "Users", path: "C:/Users" },
      { label: "Иван", path: "C:/Users/Иван" },
      { label: "HSE", path: "C:/Users/Иван/HSE" },
    ]);
  });

  it("accepts backslashes — windows users type them out of habit", () => {
    expect(toCrumbs("C:\\Users\\ivan").map((c) => c.path)).toEqual([
      "C:/",
      "C:/Users",
      "C:/Users/ivan",
    ]);
  });

  it("starts posix paths at the filesystem root", () => {
    expect(toCrumbs("/Users/ivan")).toEqual([
      { label: "/", path: "/" },
      { label: "Users", path: "/Users" },
      { label: "ivan", path: "/Users/ivan" },
    ]);
  });
});

describe("joinPath", () => {
  it("does not double the separator right after a root", () => {
    expect(joinPath("C:/", "Users")).toBe("C:/Users");
    expect(joinPath("/", "home")).toBe("/home");
  });

  it("adds the separator inside a path", () => {
    expect(joinPath("C:/Users", "ivan")).toBe("C:/Users/ivan");
  });
});

describe("parentPath", () => {
  it("walks one level up", () => {
    expect(parentPath("C:/Users/ivan")).toBe("C:/Users");
  });

  it("returns null at a root — there is nowhere above it", () => {
    expect(parentPath("C:/")).toBeNull();
    expect(parentPath("/")).toBeNull();
  });
});

describe("baseName", () => {
  it("names the chosen folder for the confirm button", () => {
    expect(baseName("C:/Users/ivan/HSE")).toBe("HSE");
  });
});

describe("isAbsoluteHostPath", () => {
  it("rejects a relative path — docker would read it as a volume name", () => {
    expect(isAbsoluteHostPath("./data")).toBe(false);
    expect(isAbsoluteHostPath("data")).toBe(false);
  });

  it("accepts both platform shapes", () => {
    expect(isAbsoluteHostPath("C:/Users")).toBe(true);
    expect(isAbsoluteHostPath("C:\\Users")).toBe(true);
    expect(isAbsoluteHostPath("/home/ivan")).toBe(true);
  });
});
