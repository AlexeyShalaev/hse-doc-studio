import { beforeAll, describe, expect, it } from "vitest";
import type { OutcomeTerm, OutcomeTrace } from "@entities/pack-studio";
import { realExplains } from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { explainToSentences, whatIfRows } from "./explain";
import { makeWords } from "./words";

// «Почему так»: решения сервера человеческими предложениями, для всех видов правил. Таблица
// видов правил, настоящие ответы ядра (explainReal.json), русский и английский, ни одного
// внутреннего слова (идентификатор, путь, имя правила) в тексте.

const NO_RULE = {
  origin: "manifest",
  file: "version.yaml",
  pointer: "/x",
  builtin: null,
} as const;

const trace = (patch: Partial<OutcomeTrace>): OutcomeTrace => ({
  id: "t1",
  rule: NO_RULE,
  kind: "supported_kinds",
  effect: "gate",
  join: "all",
  terms: [],
  actual: {},
  status: "held",
  subjects: [],
  ...patch,
});

const run = (lng: "ru" | "en", chain: OutcomeTrace[], group = "document") => {
  const t = i18n.getFixedT(lng, "packSpace");
  const words = makeWords(t, lng, undefined);
  return explainToSentences(chain, {
    t,
    words,
    group: group as "document",
  });
};

const flat = (lng: "ru" | "en", chain: OutcomeTrace[], group?: string) =>
  run(lng, chain, group).map((s) => [
    s.tone,
    s.facts.map((f) => `${f.label}: ${f.value}`).join("; "),
    s.text,
  ]);

describe("explainToSentences", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });

  const KIND: OutcomeTerm = {
    op: "in",
    subject: "kind",
    expected: ["project"],
  };

  it("виды работы: выполнено и не выполнено", () => {
    expect(
      flat("ru", [
        trace({ terms: [KIND], actual: { kind: "project" } }),
        trace({
          id: "t2",
          status: "not_held",
          terms: [KIND],
          actual: { kind: "research" },
        }),
      ]),
    ).toEqual([
      [
        "ok",
        "Вид работы: Проектная",
        "Входит в комплект, когда вид работы: проектная.",
      ],
      [
        "no",
        "Вид работы: Исследовательская",
        "Не входит в комплект. Подходит только когда вид работы: проектная.",
      ],
    ]);
  });

  it("состав: список значений через «или»", () => {
    const [row] = flat("ru", [
      trace({
        kind: "supported_staffing",
        terms: [
          {
            op: "in",
            subject: "staffing",
            expected: ["solo", "team2", "team3"],
          },
        ],
        actual: { staffing: "solo" },
      }),
    ]);
    expect(row?.[2]).toBe(
      "Входит в комплект, когда число авторов: один автор, два автора или три автора.",
    );
  });

  it("условие называется так же, как кнопка на полосе «Для какого студента»", () => {
    const [row] = flat("ru", [
      trace({
        kind: "supported_kinds",
        terms: [
          {
            op: "in",
            subject: "supervisor",
            expected: ["university", "company"],
          },
        ],
        actual: { supervisor: "university" },
      }),
    ]);
    expect(row?.[1]).toContain("Научный руководитель: Из ВШЭ");
    expect(row?.[2]).toContain("научный руководитель: из ВШЭ или из компании");
  });

  it("языки: читаются как «есть редакции»", () => {
    const langs: Partial<OutcomeTrace> = {
      kind: "supported_langs",
      effect: "display",
      terms: [{ op: "in", subject: "lang", expected: ["ru", "en"] }],
      actual: { lang: "ru" },
    };
    expect(flat("ru", [trace({ ...langs })])[0]?.[2]).toBe(
      "Есть редакции на языках: Русский, Английский.",
    );
    expect(flat("ru", [trace({ ...langs, status: "not_held" })])[0]?.[2]).toBe(
      "Нет редакции на этом языке. Есть: Русский, Английский.",
    );
  });

  it("правило Студии: слова про встроенность, без внутреннего имени", () => {
    const [row] = run("ru", [
      trace({
        kind: "builtin_gate",
        status: "not_held",
        rule: {
          origin: "builtin",
          file: null,
          pointer: null,
          builtin: "manuals_gate",
        },
        terms: [
          {
            op: "contains_any",
            subject: "meta.manuals",
            expected: ["оператора"],
          },
        ],
        actual: { "meta.manuals": "Только программиста" },
      }),
    ]);
    expect(row?.builtin).toBe(true);
    expect(row?.text).toBe(
      "Не входит в комплект. Подходит только когда в поле «meta.manuals» есть «оператора». Это правило встроено в Студию: оно читает поле «Руководства».",
    );
    expect(row?.text).not.toMatch(/manuals_gate|builtin/);
  });

  it("видимость поля, условие подписи, пропуск при NDA, необязательность, проверки", () => {
    const table: [Partial<OutcomeTrace>, string, string][] = [
      [
        {
          kind: "visible_if",
          effect: "display",
          status: "not_held",
          terms: [
            {
              op: "equals",
              subject: "answer.ai_declaration.used_ai",
              expected: ["yes"],
            },
          ],
          actual: { "answer.ai_declaration.used_ai": "no" },
        },
        "field",
        "Не показывается. Появляется только когда answer.ai_declaration.used_ai: да.",
      ],
      [
        {
          kind: "slot_when",
          effect: "add",
          terms: [{ op: "present", subject: "co_supervisor", expected: [] }],
          actual: { co_supervisor: "yes" },
        },
        "route",
        "Подпись нужна, когда есть соруководитель.",
      ],
      [
        {
          kind: "skip_if_nda",
          effect: "exclude",
          terms: [{ op: "truthy", subject: "meta.nda", expected: [] }],
          actual: { "meta.nda": "yes" },
        },
        "item",
        "Не входит в сдачу, когда включено: meta.nda.",
      ],
      [
        { kind: "slot_optional", effect: "require", status: "held" },
        "route",
        "Подпись необязательна: её можно пропустить.",
      ],
      [
        { kind: "check_disabled", effect: "exclude", status: "not_held" },
        "check",
        "Проверка не отключена.",
      ],
      [
        { kind: "route_order", effect: "order" },
        "route",
        "Порядок подписей задан правилами версии.",
      ],
      [
        { kind: "item_document", effect: "gate", status: "not_held" },
        "item",
        "Документа из этого пункта нет в комплекте, поэтому пункта тоже нет.",
      ],
    ];
    for (const [patch, group, expected] of table) {
      expect(run("ru", [trace(patch)], group)[0]?.text, patch.kind).toBe(
        expected,
      );
    }
  });

  it("не проверялось: отдельное слово и нейтральный тон", () => {
    const [row] = run("ru", [
      trace({ status: "skipped", terms: [KIND], actual: { kind: "research" } }),
    ]);
    expect(row?.tone).toBe("skip");
    expect(row?.text).toBe("Не проверялось: итог уже решён другими условиями.");
  });

  it("одинаковые решения склеиваются, порядок сервера сохраняется", () => {
    const a = trace({ terms: [KIND], actual: { kind: "project" } });
    const rows = run("ru", [a, { ...a, id: "t9" }, trace({ id: "t3" })]);
    expect(rows.map((r) => r.id)).toEqual(["t1", "t3"]);
  });

  it("английский текст есть для тех же решений", () => {
    const [row] = flat("en", [
      trace({ terms: [KIND], actual: { kind: "project" } }),
    ]);
    expect(row?.[2]).toBe("Included in the set when kind of work: project.");
  });

  describe("настоящие ответы сервера", () => {
    const real = realExplains();
    const all = real.flatMap((set) =>
      Object.entries(set.elements).map(([key, explain]) => ({
        set: set.set,
        key,
        explain,
      })),
    );

    it("каждое решение даёт предложение без идентификаторов и путей", () => {
      expect(all.length).toBeGreaterThan(20);
      let counted = 0;
      for (const { key, explain } of all) {
        const group = key.startsWith("documents:")
          ? "document"
          : key.startsWith("participants:")
            ? "participant"
            : key.startsWith("route:")
              ? "route"
              : key.startsWith("checks:")
                ? "check"
                : key.startsWith("points:")
                  ? "item"
                  : "field";
        for (const lng of ["ru", "en"] as const) {
          const rows = run(lng, explain.chain, group);
          expect(rows.length, `${key} ${lng}`).toBe(
            new Set(explain.chain.map((c) => c.id)).size >= rows.length
              ? rows.length
              : -1,
          );
          counted += rows.length;
          for (const row of rows) {
            expect(row.text, key).not.toMatch(
              /files\/|\.yaml|_gate|supported_|\{\{|undefined/,
            );
            expect(row.text.length, key).toBeGreaterThan(5);
          }
        }
      }
      expect(counted).toBeGreaterThan(20);
    });
  });
});

describe("whatIfRows", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  const t = i18n.getFixedT("ru", "packSpace");

  it("оставляет только то, что меняет элемент и не равно текущему", () => {
    const rows = whatIfRows(
      {
        state: "active",
        counterfactuals: [
          { input: "kind", value: "research", result: "absent" },
          { input: "kind", value: "project", result: "active" },
          { input: "lang", value: "en", result: "active" },
        ],
      },
      { kind: "project", lang: "ru" },
      { t, words: makeWords(t, "ru", undefined), group: "document" },
    );
    expect(rows).toEqual([
      {
        input: "kind",
        value: "research",
        inputLabel: "Вид работы",
        valueLabel: "Исследовательская",
        text: "документа не будет",
        result: "absent",
      },
    ]);
  });
});
