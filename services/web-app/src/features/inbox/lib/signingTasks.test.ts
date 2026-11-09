import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import type { SigningTaskSummary } from "@entities/signing-route";
import { formatDeadline, isOverdue, sortSigningTasks } from "./signingTasks";

const task = (
  route_id: string,
  deadline: string | null,
  since: string | null = null,
): SigningTaskSummary => ({
  project: { id: "p1", name: "ВКР" },
  route_id,
  profile: { id: "cp", name: { ru: "Точка", en: "Checkpoint" } },
  round: 1,
  sender: "Иванов И. И.",
  deadline,
  next_action: "approve",
  since,
});

const NOW = Date.parse("2026-11-10T12:00:00Z");

afterEach(async () => {
  await i18n.changeLanguage("ru");
});

describe("задачи «На подпись»", () => {
  it("просрочена, только если срок уже прошёл", () => {
    expect(isOverdue("2026-11-09T12:00:00Z", NOW)).toBe(true);
    expect(isOverdue("2026-11-11T12:00:00Z", NOW)).toBe(false);
    expect(isOverdue(null, NOW)).toBe(false);
  });

  it("сначала ближайший срок, без срока в конце, при равном сроке кто ждёт дольше", () => {
    const sorted = sortSigningTasks([
      task("none", null),
      task("later", "2026-11-20T12:00:00Z"),
      task("overdue", "2026-11-01T12:00:00Z"),
      task("soon-new", "2026-11-12T12:00:00Z", "2026-11-09T12:00:00Z"),
      task("soon-old", "2026-11-12T12:00:00Z", "2026-11-05T12:00:00Z"),
    ]);
    expect(sorted.map((t) => t.route_id)).toEqual([
      "overdue",
      "soon-old",
      "soon-new",
      "later",
      "none",
    ]);
  });

  it("срок коротко на языке интерфейса, год только не текущий", async () => {
    expect(formatDeadline("2026-11-15T12:00:00Z", NOW)).toBe("15 ноября");
    expect(formatDeadline("2027-01-15T12:00:00Z", NOW)).toBe(
      "15 января 2027 г.",
    );
    await i18n.changeLanguage("en");
    expect(formatDeadline("2026-11-15T12:00:00Z", NOW)).toBe("November 15");
  });
});
