import { describe, expect, it } from "vitest";
import {
  COURSEWORK_OUTCOME,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { summarize } from "./summary";

// Сводка только считает то, что вернул сервер: эталоны контракта дают известные числа.
describe("сводка результата", () => {
  it("ВКР: документы в комплекте, подписанты, видимые поля", () => {
    const sum = summarize(VKR_OUTCOME);
    expect(sum.documentsActive).toBe(12);
    expect(sum.documentsTotal).toBe(18);
    expect(sum.signers).toBe(2);
    expect(sum.participantsPresent).toBe(3);
    expect(sum.participantsTotal).toBe(4);
    expect(sum.metaVisible).toBe(19);
    expect(sum.points).toBe(6);
    expect(sum.routes).toBe(3);
  });

  it("дорогие части без запроса дают null, а не ноль", () => {
    const sum = summarize(VKR_OUTCOME);
    expect(sum.checksEnabled).toBeNull();
    expect(sum.branches).toBeNull();
  });

  it("курсовой проект: проверки и ветки есть", () => {
    const sum = summarize(COURSEWORK_OUTCOME);
    expect(sum.documentsActive).toBe(4);
    expect(sum.signers).toBe(4);
    expect(sum.checksTotal).toBe(39);
    expect(sum.branches).toBe(3);
  });
});
