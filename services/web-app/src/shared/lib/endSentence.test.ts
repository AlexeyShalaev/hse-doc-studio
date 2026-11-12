import { describe, expect, it } from "vitest";
import { endSentence } from "./endSentence";

describe("endSentence", () => {
  it("ставит точку после обычного имени", () => {
    expect(endSentence("Сейчас ждём: Иванов Иван")).toBe(
      "Сейчас ждём: Иванов Иван.",
    );
  });

  it("не удваивает точку после инициалов", () => {
    expect(endSentence("Сейчас ждём: Петров П. П.")).toBe(
      "Сейчас ждём: Петров П. П.",
    );
  });

  it("не трогает фразу с другим знаком конца", () => {
    expect(endSentence("Готово!")).toBe("Готово!");
    expect(endSentence("Подождите…")).toBe("Подождите…");
  });
});
