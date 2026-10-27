import { describe, expect, it } from "vitest";
import { repoLabel } from "./repoLabel";

describe("repoLabel", () => {
  it.each([
    ["https://github.com/ivan/coursework", "ivan/coursework"],
    ["https://github.com/ivan/coursework.git", "ivan/coursework"],
    ["https://gitlab.com/group/sub/repo/", "group/sub/repo"],
    ["ssh://git@github.com/ivan/coursework.git", "ivan/coursework"],
    ["https://git.example.org", "git.example.org"],
    ["file:///Users/ivan/remote.git", "/Users/ivan/remote"],
    ["not a url", "not a url"],
  ])("%s -> %s", (input, expected) => {
    expect(repoLabel(input)).toBe(expected);
  });
});
