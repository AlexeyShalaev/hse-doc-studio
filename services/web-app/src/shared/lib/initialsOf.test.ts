import { describe, expect, it } from "vitest";
import { initialsOf } from "./initialsOf";

describe("initialsOf", () => {
  it("берёт первую букву первого и последнего слова", () => {
    expect(initialsOf("Анна Петрова")).toBe("АП");
    expect(initialsOf("Мария Ивановна Сидорова")).toBe("МС");
  });

  it("для одного слова даёт одну букву, для пустого имени вопрос", () => {
    expect(initialsOf("studio")).toBe("S");
    expect(initialsOf("  ")).toBe("?");
  });
});
