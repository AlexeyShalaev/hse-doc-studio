import { describe, expect, it } from "vitest";
import { buildConflictSession, conflictDiff } from "./conflictData";

describe("демо-дифф итога слияния", () => {
  it("без выбора итог совпадает с моей версией: изменений нет", () => {
    const diff = conflictDiff("main.tex", "result");
    expect(diff.patch).toBe("");
    // Пустой дифф текстового файла не считается двоичным.
    expect(diff.binary).toBe(false);
  });

  it("учитывает сохранённый выбор по месту", () => {
    const session = buildConflictSession();
    const hunk = session.details["main.tex"];
    const key =
      hunk?.kind === "text"
        ? hunk.segments.find((s) => s.type === "hunk")
        : undefined;
    expect(key?.type).toBe("hunk");
    const diff = conflictDiff("main.tex", "result", {
      kind: "hunks",
      hunks: { [key?.type === "hunk" ? key.key : ""]: { choice: "theirs" } },
    });
    expect(diff.patch).toContain("@@");
    expect(diff.patch).toContain(
      "+Целью работы является разработка веб-приложения для совместной работы",
    );
    expect(diff.patch).toContain(
      "-Целью работы является разработка клиент-серверного приложения для",
    );
  });

  it("правка вручную целиком попадает в итог", () => {
    const diff = conflictDiff("main.tex", "result", {
      kind: "text",
      content: "Новый текст",
    });
    expect(diff.patch).toContain("+Новый текст");
  });

  it("картинка остаётся двоичной", () => {
    expect(conflictDiff("images/architecture.png", "ours").binary).toBe(true);
  });
});
