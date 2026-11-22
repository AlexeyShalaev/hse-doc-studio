import type { TFunction } from "i18next";
import { plainChange } from "./changes";
import {
  CHANGE_FIXTURES,
  FAILURE_FIXTURES,
  FINDING_FIXTURES,
  NAMING_FIXTURE,
} from "./fixtures";
import { plainFailure } from "./failure";
import { plainFinding } from "./findings";
import { makeNaming } from "./naming";

// Всё, что человек увидит из серверных сообщений: прогон слоя формулировок по фикстурам. Один
// набор для тестов слоя и для теста словаря (vocabulary.test.ts): запрещённые слова ищутся и там.

export type PlainText = { key: string; text: string };

/** Видимые тексты (без технических подробностей) на языке `lng`; `named`: с названиями из пака или без них. */
export const plainTexts = (
  t: TFunction,
  lng: string,
  named: boolean,
): PlainText[] => {
  const naming = makeNaming({ lng, t, ...(named ? NAMING_FIXTURE : {}) });
  const rows: PlainText[] = [];
  for (const { rule, variant, finding } of FINDING_FIXTURES) {
    const plain = plainFinding(finding, naming, t);
    const key = `${rule}${variant === "" ? "" : `.${variant}`}`;
    rows.push({ key: `finding.${key}.title`, text: plain.title });
    rows.push({ key: `finding.${key}.how`, text: plain.how });
    if (plain.extra !== null) {
      rows.push({ key: `finding.${key}.extra`, text: plain.extra });
    }
  }
  for (const input of FAILURE_FIXTURES) {
    const plain = plainFailure(input, t);
    const key = `${input.code ?? "none"}${input.offline === true ? ".offline" : ""}`;
    rows.push({ key: `failure.${key}.title`, text: plain.title });
    rows.push({ key: `failure.${key}.how`, text: plain.how });
  }
  for (const change of CHANGE_FIXTURES) {
    const plain = plainChange(change, naming, t);
    const key = `${change.kind}.${change.id}`;
    rows.push({ key: `change.${key}.label`, text: plain.label });
    for (const [side, value] of [
      ["before", plain.before],
      ["after", plain.after],
    ] as const) {
      if (value !== null)
        rows.push({ key: `change.${key}.${side}`, text: value });
    }
  }
  return rows;
};
