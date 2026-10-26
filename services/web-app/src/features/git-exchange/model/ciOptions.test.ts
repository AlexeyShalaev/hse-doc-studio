import { describe, expect, it } from "vitest";
import {
  DEFAULT_CI_OPTIONS,
  ciFileState,
  ciProblems,
  ciRequestKey,
  toCiRequest,
  toggleDoc,
  toggleTrigger,
} from "./ciOptions";

describe("настройки автосборки", () => {
  it("по умолчанию собирает все документы при изменениях в основной ветке", () => {
    expect(toCiRequest(DEFAULT_CI_OPTIONS)).toEqual({
      provider: "github",
      docs: "all",
      publish: "artifacts",
      triggers: ["push"],
    });
    expect(ciProblems(DEFAULT_CI_OPTIONS)).toEqual([]);
  });

  it("отправляет выбранные документы списком, а образ только если его изменили", () => {
    const request = toCiRequest({
      ...DEFAULT_CI_OPTIONS,
      docsMode: "selected",
      docs: ["thesis", "annotation"],
      image: "  ghcr.io/me/builder:1  ",
    });
    expect(request.docs).toEqual(["thesis", "annotation"]);
    expect(request.image).toBe("ghcr.io/me/builder:1");
    expect(
      toCiRequest({ ...DEFAULT_CI_OPTIONS, image: "   " }),
    ).not.toHaveProperty("image");
  });

  it("держит порядок запусков постоянным, чтобы тот же выбор давал тот же файл", () => {
    const a = toCiRequest({
      ...DEFAULT_CI_OPTIONS,
      triggers: ["manual", "push"],
    });
    const b = toCiRequest({
      ...DEFAULT_CI_OPTIONS,
      triggers: ["push", "manual"],
    });
    expect(a.triggers).toEqual(["push", "manual"]);
    expect(ciRequestKey(a)).toBe(ciRequestKey(b));
  });

  it("называет, что мешает записать файл", () => {
    expect(
      ciProblems({ ...DEFAULT_CI_OPTIONS, docsMode: "selected", docs: [] }),
    ).toEqual(["no_documents"]);
    expect(ciProblems({ ...DEFAULT_CI_OPTIONS, triggers: [] })).toEqual([
      "no_triggers",
    ]);
    expect(
      ciProblems({
        ...DEFAULT_CI_OPTIONS,
        docsMode: "selected",
        docs: [],
        triggers: [],
      }),
    ).toEqual(["no_documents", "no_triggers"]);
  });

  it("переключает запуски и документы, не меняя исходные списки", () => {
    const triggers = ["push"] as const;
    expect(toggleTrigger([...triggers], "tag")).toEqual(["push", "tag"]);
    expect(toggleTrigger(["push", "tag"], "push")).toEqual(["tag"]);
    expect(triggers).toEqual(["push"]);
    expect(toggleDoc(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleDoc(["a", "b"], "a")).toEqual(["b"]);
  });

  it("различает новый, совпадающий и отличающийся файл", () => {
    expect(ciFileState({ exists: false, same: false })).toBe("new");
    expect(ciFileState({ exists: true, same: true })).toBe("same");
    expect(ciFileState({ exists: true, same: false })).toBe("differs");
  });
});
