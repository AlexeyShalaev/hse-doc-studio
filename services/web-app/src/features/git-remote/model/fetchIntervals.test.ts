import { describe, expect, it } from "vitest";
import {
  DEFAULT_INTERVAL_CHOICE,
  intervalChoiceValue,
  intervalChoices,
  parseIntervalChoice,
  splitInterval,
} from "./fetchIntervals";

describe("интервалы фоновой проверки", () => {
  it("готовые значения идут по возрастанию и не меньше минуты", () => {
    expect(intervalChoices()).toEqual([60, 120, 300, 600, 900, 1800]);
  });

  it("действующее нестандартное значение добавляется в список один раз", () => {
    expect(intervalChoices(450, 450, 300)).toEqual([
      60, 120, 300, 450, 600, 900, 1800,
    ]);
  });

  it("ноль, пустое и отрицательное значения в список не попадают", () => {
    expect(intervalChoices(0, null, undefined, -5)).toEqual(intervalChoices());
  });

  it("интервал, равный умолчанию, показывается как «по умолчанию»", () => {
    expect(intervalChoiceValue(300, 300)).toBe(DEFAULT_INTERVAL_CHOICE);
    expect(intervalChoiceValue(600, 300)).toBe("600");
  });

  it("«по умолчанию» уходит на сервер как null, число как секунды", () => {
    expect(parseIntervalChoice(DEFAULT_INTERVAL_CHOICE)).toBeNull();
    expect(parseIntervalChoice("900")).toBe(900);
    expect(parseIntervalChoice("мусор")).toBeNull();
    expect(parseIntervalChoice("0")).toBeNull();
  });

  it("минуты и целые часы разделяются для подписи", () => {
    expect(splitInterval(60)).toEqual({ unit: "minutes", count: 1 });
    expect(splitInterval(1800)).toEqual({ unit: "minutes", count: 30 });
    expect(splitInterval(3600)).toEqual({ unit: "hours", count: 1 });
    expect(splitInterval(5400)).toEqual({ unit: "minutes", count: 90 });
  });
});
