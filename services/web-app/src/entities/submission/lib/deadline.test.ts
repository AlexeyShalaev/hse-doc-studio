import { describe, expect, it } from "vitest";
import {
  daysUntilDeadline,
  deadlineFromInput,
  deadlineToInput,
  formatDeadlineDay,
  formatDeadlineTime,
  routeDeadlineFromPoint,
  sameMoment,
  toMoscowIso,
} from "./deadline";

// Срок точки по Москве (signing-route.md, 16.3 и 16.6): пояс UTC+3, дни по календарю Москвы.

const at = (iso: string) => Date.parse(iso);

describe("срок точки: ввод по Москве", () => {
  it("дата и время формы дают момент с поясом +03:00", () => {
    expect(deadlineFromInput("2026-11-15", "23:59")).toBe(
      "2026-11-15T23:59:00+03:00",
    );
    expect(deadlineFromInput("2026-11-15", "")).toBe(
      "2026-11-15T23:59:00+03:00",
    );
    expect(deadlineFromInput("2026-11-15", "00:30")).toBe(
      "2026-11-15T00:30:00+03:00",
    );
  });

  it("неразборчивая дата или время не дают срока", () => {
    expect(deadlineFromInput("", "23:59")).toBeNull();
    expect(deadlineFromInput("2026-02-31", "23:59")).toBeNull();
    expect(deadlineFromInput("2026-11-15", "24:00")).toBeNull();
    expect(deadlineFromInput("15.11.2026", "23:59")).toBeNull();
  });

  it("срок в любом поясе раскладывается в поля по Москве", () => {
    expect(deadlineToInput("2026-11-15T20:59:00Z")).toEqual({
      date: "2026-11-15",
      time: "23:59",
    });
    expect(deadlineToInput("2026-11-15T21:30:00Z")).toEqual({
      date: "2026-11-16",
      time: "00:30",
    });
    expect(deadlineToInput(null)).toEqual({ date: "", time: "23:59" });
  });

  it("toMoscowIso пишет момент, как сервер", () => {
    expect(toMoscowIso(at("2026-11-14T20:59:00Z"))).toBe(
      "2026-11-14T23:59:00+03:00",
    );
  });
});

describe("срок точки: показ", () => {
  const now = at("2026-11-12T10:00:00+03:00");

  it("день и время по Москве, год только чужой", () => {
    expect(formatDeadlineDay("2026-11-15T23:59:00+03:00", now)).toBe("15.11");
    expect(formatDeadlineDay("2027-01-20T23:59:00+03:00", now)).toBe(
      "20.01.2027",
    );
    expect(formatDeadlineTime("2026-11-15T20:59:00Z")).toBe("23:59");
  });

  it("дни считаются по календарю Москвы, а не сутками до момента", () => {
    // 14.11 вечером срок 15.11 в 10:00: «через 1 день», хотя до него меньше суток.
    expect(
      daysUntilDeadline(
        "2026-11-15T10:00:00+03:00",
        at("2026-11-14T22:00:00+03:00"),
      ),
    ).toBe(1);
    // 23:30 UTC 14.11 это уже 15.11 по Москве: срок сегодня.
    expect(
      daysUntilDeadline(
        "2026-11-15T23:59:00+03:00",
        at("2026-11-14T21:30:00Z"),
      ),
    ).toBe(0);
    expect(daysUntilDeadline("2026-11-15T23:59:00+03:00", now)).toBe(3);
    expect(daysUntilDeadline("2026-11-10T23:59:00+03:00", now)).toBe(-2);
  });

  it("один момент в разных поясах совпадает", () => {
    expect(
      sameMoment("2026-11-15T23:59:00+03:00", "2026-11-15T20:59:00.000Z"),
    ).toBe(true);
    expect(sameMoment(null, null)).toBe(true);
    expect(sameMoment("2026-11-15T23:59:00+03:00", null)).toBe(false);
  });
});

describe("срок маршрута из срока точки (16.5)", () => {
  const now = at("2026-11-10T12:00:00+03:00");

  it("на сутки раньше в то же время", () => {
    expect(routeDeadlineFromPoint("2026-11-15T23:59:00+03:00", now)).toBe(
      "2026-11-14T23:59:00+03:00",
    );
  });

  it("ближе двух суток равен сроку точки", () => {
    expect(routeDeadlineFromPoint("2026-11-12T10:00:00+03:00", now)).toBe(
      "2026-11-12T10:00:00+03:00",
    );
  });

  it("прошедший или пустой срок точки не даёт срока маршрута", () => {
    expect(routeDeadlineFromPoint("2026-11-09T23:59:00+03:00", now)).toBeNull();
    expect(routeDeadlineFromPoint(null, now)).toBeNull();
  });
});
