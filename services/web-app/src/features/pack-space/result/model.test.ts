import { beforeAll, describe, expect, it } from "vitest";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import {
  countResult,
  groupDocuments,
  groupFields,
  headline,
  leadLine,
  matchesQuery,
  partSummary,
  routeText,
  shortName,
} from "./model";
import { makeReasoner } from "./reasons";

const t = i18n.getFixedT("ru", "packSpace");

describe("модель центра «Результата»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });

  it("числа берутся из ответа сервера", () => {
    const course = countResult(COURSEWORK_OUTCOME);
    expect(course).toMatchObject({
      documents: 4,
      people: 4,
      deadlines: 4,
      signatures: 6,
      signedPoints: 2,
      signers: 4,
    });
    const vkr = countResult(VKR_OUTCOME);
    expect(vkr.documents).toBe(12);
    // Руководителя «соруководитель» нет: в подписантах его не считаем.
    expect(vkr.people).toBe(3);
  });

  it("заголовок и строка под ним склоняются", () => {
    const base = countResult(COURSEWORK_OUTCOME);
    expect(headline(t, { ...base, documents: 1 })).toBe(
      "Студент получит 1 документ",
    );
    expect(headline(t, { ...base, documents: 2 })).toBe(
      "Студент получит 2 документа",
    );
    expect(headline(t, { ...base, documents: 5 })).toBe(
      "Студент получит 5 документов",
    );
    expect(headline(t, { ...base, documents: 0 })).toBe(
      "Студент не получит ни одного документа",
    );
    expect(leadLine(t, { ...base, signers: 1, deadlines: 3 })).toBe(
      "Подписывает 1 человек, сдача в 3 точках.",
    );
    expect(leadLine(t, { ...base, signers: 0, deadlines: 0 })).toBe(
      "Подписи не нужны, сдавать ничего не нужно.",
    );
  });

  it("итоги свёрнутых частей", () => {
    const counts = countResult(COURSEWORK_OUTCOME);
    expect(partSummary(t, "ru", COURSEWORK_OUTCOME, counts, "signatures")).toBe(
      "6 подписей в 2 точках",
    );
    expect(
      partSummary(t, "ru", VKR_OUTCOME, countResult(VKR_OUTCOME), "people"),
    ).toBe("автор, руководитель из ВШЭ, академический руководитель из ВШЭ");
  });

  it("порядок подписания словами; параллельные шаги через «и»", () => {
    const point = COURSEWORK_OUTCOME.points[0];
    if (!point) throw new Error("нет точки");
    expect(routeText(t, COURSEWORK_OUTCOME, point)).toBe(
      "Автор, затем руководитель и соруководитель, затем академический руководитель",
    );
    const none = COURSEWORK_OUTCOME.points[1];
    if (!none) throw new Error("нет точки");
    expect(routeText(t, COURSEWORK_OUTCOME, none)).toBe("");
  });

  it("короткое имя точки и поиск", () => {
    expect(shortName("КТ3 — Итоговая аттестация")).toBe("КТ3");
    expect(shortName("Предзащита КП")).toBe("Предзащита КП");
    expect(matchesQuery(" ПРЕЗ ", "Презентация защиты", null)).toBe(true);
    expect(matchesQuery("zzz", "Презентация", null)).toBe(false);
    expect(matchesQuery("", null)).toBe(true);
  });

  it("группы идут в порядке появления, без группы в конце", () => {
    const groups = groupDocuments(VKR_OUTCOME.documents);
    expect(groups.at(-1)?.id === "" || groups.every((g) => g.id !== "")).toBe(
      true,
    );
    expect(groups.map((group) => group.id)).toContain("espd");
    const fields = groupFields(VKR_OUTCOME.meta);
    expect(fields.at(-1)?.id).toBe("");
  });
});

describe("причины «не вошло»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });

  const reasoner = makeReasoner(t, "ru", VKR_OUTCOME, VKR_INPUTS.inputs);

  it("условие пересказано словами, действие ставит нужное значение", () => {
    const doc = VKR_OUTCOME.documents.find(
      (item) => item.id === "shared_technical_specification",
    );
    const reason = reasoner.why(doc?.why ?? []);
    expect(reason?.text).toBe(
      "Число авторов: нужно «два автора, три автора», сейчас «один автор».",
    );
    expect(reason?.action).toEqual({
      input: "staffing",
      value: "team2",
      label: "Число авторов: два автора",
    });
  });

  it("выключенное условие включается кнопкой, включённое нет", () => {
    expect(reasoner.turnOn("co_supervisor")).toEqual({
      input: "co_supervisor",
      value: "yes",
      label: "Соруководитель: да",
    });
    expect(reasoner.turnOn("academic_supervisor")).toBeNull();
    expect(reasoner.turnOn("нет такого")).toBeNull();
  });

  it("нет решений сервера: причины нет, показываем запасной текст", () => {
    expect(reasoner.why([])).toBeNull();
    expect(reasoner.why(["нет-такого"])).toBeNull();
  });

  it("на курсовом проекте тоже работает (другой набор условий)", () => {
    const course = makeReasoner(
      t,
      "ru",
      COURSEWORK_OUTCOME,
      COURSEWORK_INPUTS.inputs,
    );
    expect(course.subject("kind")).toBe("Вид работы");
  });
});
