import { describe, expect, it } from "vitest";
import {
  insertMention,
  mentionQueryAt,
  mentionsInText,
  splitMentions,
} from "./mentions";

describe("mentions", () => {
  it("finds the query after @ before the caret", () => {
    expect(mentionQueryAt("Привет @Бор", 11)).toEqual({
      query: "Бор",
      start: 7,
    });
    expect(mentionQueryAt("@", 1)).toEqual({ query: "", start: 0 });
    expect(mentionQueryAt("почта a@b", 9)).toBeNull();
    expect(mentionQueryAt("без упоминания", 5)).toBeNull();
  });

  it("replaces the typed query with the picked name", () => {
    const at = { query: "Бор", start: 7 };
    expect(insertMention("Привет @Бор, глянь", at, "Борис")).toEqual({
      text: "Привет @Борис , глянь",
      caret: 14,
    });
  });

  it("keeps only picked mentions that survive in the text", () => {
    const picked = [
      { userId: "u1", name: "Борис" },
      { userId: "u2", name: "Вера" },
    ];
    expect(mentionsInText("@Борис посмотри", picked)).toEqual(["u1"]);
    expect(mentionsInText("уже без упоминаний", picked)).toEqual([]);
  });

  it("splits text for highlighting", () => {
    expect(splitMentions("Привет @Борис и @Вера!")).toEqual([
      { text: "Привет ", mention: false },
      { text: "@Борис", mention: true },
      { text: " и ", mention: false },
      { text: "@Вера", mention: true },
      { text: "!", mention: false },
    ]);
  });
});
