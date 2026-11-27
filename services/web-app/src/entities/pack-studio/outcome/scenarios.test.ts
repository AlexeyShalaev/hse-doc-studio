import { beforeAll, describe, expect, it } from "vitest";
import {
  PackStaleFileError,
  ScenarioAssertionSchema,
  type PackScenario,
  type PackScenarioEntry,
  type PackScenarioRun,
  type ScenarioAssertion,
} from "@entities/pack-studio";
import {
  COURSEWORK_OUTCOME,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import {
  ASSERTION_KINDS,
  assertionKey,
  badgeOf,
  classifyFailure,
  describeAssertion,
  fieldOfReason,
  formOf,
  formVersions,
  freeId,
  idProblem,
  inputChanges,
  mergedInputs,
  modeOf,
  namesOf,
  nameProblem,
  notPassing,
  requestOf,
  resultsById,
  retryable,
  seriesOf,
  slugify,
  splitPatterns,
  suggestAssertions,
  tallyOf,
} from "./scenarios";

const company = (): PackScenarioEntry => {
  const entry = COURSEWORK_SCENARIOS.scenarios.find(
    (e) => e.id === "company-supervisor",
  );
  if (!entry) throw new Error("fixture");
  return structuredClone(entry);
};
const scenarioOf = (): PackScenario => {
  const scenario = company().scenario;
  if (!scenario) throw new Error("fixture");
  return scenario;
};

describe("имя файла сценария", () => {
  it("транслитерирует название и оставляет латиницу и цифры через дефис", () => {
    expect(slugify("Научрук из компании, есть консультант")).toBe(
      "nauchruk-iz-kompanii-est-konsultant",
    );
    expect(slugify("NDA и только руководство программиста")).toBe(
      "nda-i-tolko-rukovodstvo-programmista",
    );
    expect(slugify("  --  ")).toBe("");
    expect(slugify("а".repeat(80)).length).toBeLessThanOrEqual(64);
  });

  it("подбирает первое свободное имя", () => {
    expect(freeId("a", new Set())).toBe("a");
    expect(freeId("a", new Set(["a"]))).toBe("a-2");
    expect(freeId("a", new Set(["a", "a-2"]))).toBe("a-3");
    expect(freeId("", new Set())).toBe("scenario");
    expect(
      freeId("x".repeat(64), new Set(["x".repeat(64)])).length,
    ).toBeLessThanOrEqual(64);
  });

  it("проверяет формат так же, как сервер", () => {
    expect(idProblem("")).toBe("empty");
    expect(idProblem("company-supervisor")).toBeNull();
    expect(idProblem("Company")).toBe("format");
    expect(idProblem("a--b")).toBe("format");
    expect(idProblem("-a")).toBe("format");
    expect(idProblem("a".repeat(65))).toBe("format");
  });
});

describe("версии сценария", () => {
  it("серия берётся из номера из трёх чисел", () => {
    expect(seriesOf("2026.1.6")).toBe("2026.1.*");
    expect(seriesOf("beta")).toBeNull();
  });

  it("режим по списку из файла и обратно", () => {
    expect(modeOf(undefined, "2026.1.6").mode).toBe("any");
    expect(modeOf(["2026.1.6"], "2026.1.6").mode).toBe("this");
    expect(modeOf(["2026.1.*"], "2026.1.6").mode).toBe("series");
    expect(modeOf(["2026.2.*", "2026.1.1"], "2026.1.6")).toEqual({
      mode: "custom",
      custom: "2026.2.*, 2026.1.1",
    });
    expect(splitPatterns("2026.1.*, 2026.2.1;  x")).toEqual([
      "2026.1.*",
      "2026.2.1",
      "x",
    ]);
    const form = formOf(null, "2026.1.6", "");
    expect(formVersions({ ...form, versionsMode: "any" }, "2026.1.6")).toEqual(
      [],
    );
    expect(formVersions({ ...form, versionsMode: "this" }, "2026.1.6")).toEqual(
      ["2026.1.6"],
    );
    expect(
      formVersions({ ...form, versionsMode: "series" }, "2026.1.6"),
    ).toEqual(["2026.1.*"]);
    expect(formVersions({ ...form, versionsMode: "series" }, "beta")).toEqual([
      "beta",
    ]);
    expect(
      formVersions(
        { ...form, versionsMode: "custom", versionsCustom: "a, b" },
        "1",
      ),
    ).toEqual(["a", "b"]);
  });
});

describe("готовые утверждения", () => {
  it("сервер принимает все: каждое проходит строгую схему", () => {
    for (const outcome of [COURSEWORK_OUTCOME, VKR_OUTCOME]) {
      for (const assertion of suggestAssertions(outcome)) {
        expect(ScenarioAssertionSchema.safeParse(assertion).success).toBe(true);
      }
    }
  });

  it("курсовой даёт все семь видов", () => {
    const kinds = new Set(
      suggestAssertions(COURSEWORK_OUTCOME).map((a) => a.kind),
    );
    expect([...kinds].sort()).toEqual([...ASSERTION_KINDS].sort());
  });

  it("берёт состояния как есть: «есть документ» и «нет документа» из ответа", () => {
    const states = new Map(
      suggestAssertions(VKR_OUTCOME).flatMap((a) =>
        a.kind === "document_state" ? [[a.doc, a.state] as const] : [],
      ),
    );
    for (const doc of VKR_OUTCOME.documents) {
      expect(states.get(doc.id)).toBe(doc.state);
    }
    expect([...states.values()]).toContain("inactive");
    const count = suggestAssertions(VKR_OUTCOME).find(
      (a) => a.kind === "document_count",
    );
    expect(count).toMatchObject({
      state: "active",
      count: VKR_OUTCOME.documents.filter((d) => d.state === "active").length,
    });
  });

  it("подписанты и шаги маршрута точки из ответа", () => {
    const list = suggestAssertions(COURSEWORK_OUTCOME);
    const steps = list.find(
      (a) => a.kind === "route_steps" && a.point === "topic-approval",
    );
    expect(steps).toMatchObject({
      steps: [
        ["author"],
        ["supervisor", "co_supervisor"],
        ["academic_supervisor"],
      ],
    });
    expect(
      list.some(
        (a) =>
          a.kind === "route_pair" &&
          a.persona === "academic_supervisor" &&
          a.present,
      ),
    ).toBe(true);
  });

  it("ключ не зависит от порядка внутри шага", () => {
    expect(
      assertionKey({
        kind: "route_steps",
        point: "p",
        steps: [["b", "a"], ["c"]],
      }),
    ).toBe(
      assertionKey({
        kind: "route_steps",
        point: "p",
        steps: [["a", "b"], ["c"]],
      }),
    );
    expect(
      assertionKey({
        kind: "participant_present",
        persona: "a",
        present: true,
      }),
    ).not.toBe(
      assertionKey({
        kind: "participant_present",
        persona: "a",
        present: false,
      }),
    );
  });
});

describe("подписи утверждений", () => {
  beforeAll(async () => {
    await loadPackOutcomeNamespace();
  });

  it.each([
    ["ru", "Документ «Заявка на тему» есть в комплекте"],
    ["en", 'Document "Topic application" is in the set'],
  ])("человеческими словами (%s)", async (lng, expected) => {
    await i18n.changeLanguage(lng);
    const t = i18n.getFixedT(lng, "packOutcome");
    const names = namesOf(
      {
        ...COURSEWORK_OUTCOME,
        documents: COURSEWORK_OUTCOME.documents.map((d) =>
          d.id === "topic_application"
            ? { ...d, name: { ru: "Заявка на тему", en: "Topic application" } }
            : d,
        ),
      },
      lng,
      t,
    );
    expect(
      describeAssertion(
        { kind: "document_state", doc: "topic_application", state: "active" },
        names,
        t,
      ),
    ).toBe(expected);
    await i18n.changeLanguage("ru");
  });

  it("все семь видов и состояния имеют текст, ключи не торчат", async () => {
    await i18n.changeLanguage("ru");
    const t = i18n.getFixedT("ru", "packOutcome");
    const names = namesOf(COURSEWORK_OUTCOME, "ru", t);
    const all: ScenarioAssertion[] = [
      ...suggestAssertions(COURSEWORK_OUTCOME),
      { kind: "document_state", doc: "x", state: "absent" },
      { kind: "document_state", doc: "x", state: "inactive" },
      { kind: "document_count", state: "inactive", count: 2 },
      { kind: "participant_present", persona: "author2", present: false },
      { kind: "item_active", point: "p", doc: "d", active: false },
      {
        kind: "route_pair",
        point: "p",
        doc: "d",
        slot: "s",
        persona: "supervisor",
        present: false,
      },
      { kind: "route_steps", point: "p", steps: [] },
      {
        kind: "route_pair",
        point: "p",
        doc: "d",
        slot: "s",
        persona: "supervisor",
        present: true,
        optional: true,
      },
    ];
    for (const assertion of all) {
      const text = describeAssertion(assertion, names, t);
      expect(text, assertion.kind).not.toMatch(/scenarios\.|\{\{/);
      expect(text.length).toBeGreaterThan(5);
    }
  });

  it("необязательность подписи читается из файла, называется и различает утверждения", () => {
    const pair = {
      kind: "route_pair",
      point: "p",
      doc: "d",
      slot: "s",
      persona: "supervisor",
      present: true,
    } as const;
    const optional = ScenarioAssertionSchema.parse({ ...pair, optional: true });
    const unset = ScenarioAssertionSchema.parse({ ...pair, optional: null });
    const t = i18n.getFixedT("ru", "packOutcome");
    const names = namesOf(COURSEWORK_OUTCOME, "ru", t);

    expect(describeAssertion(optional, names, t)).toContain(
      "подпись необязательна",
    );
    expect(describeAssertion({ ...pair, optional: false }, names, t)).toContain(
      "подпись обязательна",
    );
    expect(describeAssertion(unset, names, t)).not.toContain("обязательна");
    expect(assertionKey(unset)).toBe(assertionKey(pair));
    expect(assertionKey(optional)).not.toBe(assertionKey(pair));
  });
});

describe("тело записи", () => {
  const source = (base: PackScenario | null) => ({
    base,
    inputs: { supervisor: "company" },
    example: "auto:normal",
    version: "2026.1.6",
    state: "work_tree" as const,
  });

  it("новый сценарий: снимок просит записать сервер, версии серией", () => {
    const form = {
      ...formOf(null, "2026.1.6", "x"),
      name: { ru: " Имя ", en: "" },
    };
    const body = requestOf(form, source(null));
    expect(body).toEqual({
      scenario: {
        format: 1,
        name: { ru: "Имя" },
        example: "auto:normal",
        inputs: { supervisor: "company" },
        versions: ["2026.1.*"],
      },
      record_snapshot: "work_tree",
      version: "2026.1.6",
    });
  });

  it("правка: снимок остаётся прежним, чужие языки не теряются", () => {
    const base = {
      ...scenarioOf(),
      name: { ru: "Старое", de: "Alt" },
    };
    const form = formOf(base, "2026.1.6", "company-supervisor");
    form.name.ru = "Новое";
    const body = requestOf(form, source(base));
    expect(body.record_snapshot).toBeUndefined();
    expect(body.scenario.snapshot).toEqual(base.snapshot);
    expect(body.scenario.name).toEqual({ ru: "Новое", de: "Alt" });
    expect(body.scenario.assertions).toEqual(base.assertions);
  });

  it("снимок заново, без снимка, очищенное описание", () => {
    const base = scenarioOf();
    const form = formOf(base, "2026.1.6", "x");
    const again = requestOf({ ...form, recordSnapshot: true }, source(base));
    expect(again.record_snapshot).toBe("work_tree");
    expect(again.scenario.snapshot).toBeUndefined();
    const none = requestOf(
      { ...form, snapshot: false, recordSnapshot: false },
      source(base),
    );
    expect(none.record_snapshot).toBeUndefined();
    expect(none.scenario.snapshot).toBeUndefined();
    const noDescription = requestOf(
      { ...form, description: { ru: "", en: "" } },
      source(base),
    );
    expect(noDescription.scenario.description).toBeUndefined();
  });

  it("у сценария без снимка галочка снимка записывает его", () => {
    const base = { ...scenarioOf(), snapshot: null };
    const form = { ...formOf(base, "2026.1.6", "x"), snapshot: true };
    expect(requestOf(form, source(base)).record_snapshot).toBe("work_tree");
  });

  it("название обязательно хотя бы на одном языке", () => {
    const form = formOf(null, "2026.1.6", "x");
    expect(nameProblem(form)).toBe(true);
    expect(nameProblem({ ...form, name: { ru: "", en: " x " } })).toBe(false);
  });

  it("вводные нового сценария: выбранный сценарий и изменения поверх", () => {
    expect(
      mergedInputs(COURSEWORK_SCENARIOS, "company-supervisor", {
        supervisor: "none",
      }),
    ).toEqual({ supervisor: "none", co_supervisor: "yes" });
    expect(mergedInputs(COURSEWORK_SCENARIOS, null, { a: "1" })).toEqual({
      a: "1",
    });
    expect(
      inputChanges({ a: "1", b: "2" }, { a: "1", b: "3", c: "4" }),
    ).toEqual([
      { id: "b", before: "2", after: "3" },
      { id: "c", before: null, after: "4" },
    ]);
  });
});

describe("прогон: значки и итог", () => {
  const run: PackScenarioRun = COURSEWORK_RUN;
  const entries = COURSEWORK_SCENARIOS.scenarios;

  it("статус сценария из прогона, битый файл всегда виден", () => {
    const results = resultsById(run);
    const status = (
      id: string,
      state: "loading" | "failed" | "ready" = "ready",
    ) => {
      const entry = entries.find((e) => e.id === id);
      if (!entry) throw new Error(id);
      return badgeOf(entry, results, state);
    };
    expect(status("company-supervisor")).toBe("passed");
    expect(status("university-supervisor")).toBe("failed");
    expect(status("draft", "loading")).toBe("broken");
    expect(badgeOf(company(), new Map(), "loading")).toBe("pending");
    expect(badgeOf(company(), new Map(), "failed")).toBe("unknown");
  });

  it("итог из ответа сервера и битые файлы", () => {
    const tally = tallyOf(entries, run);
    expect(tally).toMatchObject({
      passed: 2,
      failed: 1,
      errors: 0,
      broken: 1,
      total: 3,
    });
    expect(notPassing(tally)).toBe(1);
    expect(tallyOf(entries, undefined).passed).toBe(0);
  });
});

describe("отказы сервера", () => {
  it("разбирает коды в виды", () => {
    expect(classifyFailure(new PackStaleFileError(null, '"e"'))).toEqual({
      kind: "stale",
      diskEtag: '"e"',
    });
    expect(
      classifyFailure(new ApiError("x", "stale_file", 409, { etag: '"d"' })),
    ).toEqual({ kind: "stale", diskEtag: '"d"' });
    expect(classifyFailure(new ApiError("x", "scenario_taken", 409))).toEqual({
      kind: "taken",
    });
    expect(
      classifyFailure(new ApiError("x", "scenario_not_found", 404)),
    ).toEqual({ kind: "missing" });
    expect(
      classifyFailure(
        new ApiError("x", "scenario_invalid", 400, {
          reason: "assertions[2].kind: unknown kind",
        }),
      ),
    ).toEqual({
      kind: "invalid",
      reason: "assertions[2].kind: unknown kind",
      field: "assertions",
    });
    expect(classifyFailure(new ApiError("x", "n", 0))).toEqual({
      kind: "offline",
    });
    expect(classifyFailure(new ApiError("x", "internal_error", 500))).toEqual({
      kind: "server",
    });
    expect(classifyFailure(new ApiError("x", "outcome_busy", 503))).toEqual({
      kind: "busy",
    });
    expect(
      classifyFailure(new ApiError("x", "path_not_allowed", 400)).kind,
    ).toBe("other");
    expect(classifyFailure(new Error("boom")).kind).toBe("other");
  });

  it("повторять имеет смысл только сеть, сбой и занятый сервер", () => {
    expect(retryable({ kind: "offline" })).toBe(true);
    expect(retryable({ kind: "server" })).toBe(true);
    expect(retryable({ kind: "busy" })).toBe(true);
    expect(retryable({ kind: "taken" })).toBe(false);
    expect(retryable({ kind: "stale", diskEtag: null })).toBe(false);
    expect(fieldOfReason("id: bad")).toBe("id");
    expect(fieldOfReason("")).toBeNull();
  });
});
