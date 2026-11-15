import { describe, expect, it } from "vitest";
import { hostOfUrl } from "./hostOfUrl";

describe("hostOfUrl", () => {
  it.each([
    ["https://GitHub.com/owner/packs", "github.com"],
    ["git@gitlab.example.org:fcs/packs.git", "gitlab.example.org"],
    ["ssh://git@git.hse.ru:2222/packs.git", "git.hse.ru"],
    ["", null],
    ["not a url", null],
  ])("%s → %s", (url, host) => {
    expect(hostOfUrl(url)).toBe(host);
  });
});
