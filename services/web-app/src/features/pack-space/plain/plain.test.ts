import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import banned from "../vocabulary.banned.json";
import { plainChange } from "./changes";
import {
  FAILURE_FAMILIES,
  KNOWN_FAILURE_CODES,
  failureInput,
  familyOf,
  plainFailure,
} from "./failure";
import {
  FINDING_FIXTURES,
  FIXTURE_IDS,
  NAMING_FIXTURE,
  CHANGE_FIXTURES,
  RAW_DOCKER,
} from "./fixtures";
import { LINT_RULES, plainFinding } from "./findings";
import { makeNaming } from "./naming";
import { plainTexts } from "./textsKit";

// Слой человеческих формулировок (pack-studio-ux.md, 5.7 и P5): полнота по серверу, слова, названия
// из пака, идентификаторы только в технических подробностях.

const API = join(import.meta.dirname, "../../../../../api/hse_doc_studio");
const server = (path: string): string => readFileSync(join(API, path), "utf8");

let tr: TFunction;
const setLang = async (lng: "ru" | "en") => {
  await i18n.changeLanguage(lng);
  tr = i18n.getFixedT(lng, "packSpace");
};

beforeAll(async () => {
  await loadPackSpaceNamespace();
});

describe("полнота по серверу", () => {
  it("каждое правило линтера результата (RULES сервера) имеет слова, и наоборот", () => {
    const text = server("core/pack_studio/outcome/lint.py");
    const block = /^RULES:[\s\S]*?^\)/m.exec(text)?.[0] ?? "";
    const rules = [...block.matchAll(/^\s+\("([a-z-]+)",\s*"/gm)].map(
      (match) => match[1],
    );
    expect(rules).toHaveLength(22);
    expect([...LINT_RULES].sort()).toEqual([...rules].sort());
  });

  it("на каждое правило есть хотя бы одна фикстура", () => {
    const covered = new Set(FINDING_FIXTURES.map((item) => item.rule));
    expect([...covered].sort()).toEqual([...LINT_RULES].sort());
  });

  it("каждый код причины сбоя сборки на сервере отнесён к объяснению", () => {
    const failure = server("core/compile/failure.py");
    const codes = new Set<string>();
    for (const match of failure.matchAll(/^[A-Z_]+ = "([a-z_]+)"$/gm)) {
      if (match[1]) codes.add(match[1]);
    }
    for (const match of failure.matchAll(/^ {4}"([a-z_]+)": \($/gm)) {
      if (match[1]) codes.add(match[1]);
    }
    for (const match of failure.matchAll(/^ {4}([A-Z_]+): \($/gm)) {
      const name = match[1] ?? "";
      const value = new RegExp(`^${name} = "([a-z_]+)"$`, "m").exec(
        failure,
      )?.[1];
      if (value) codes.add(value);
    }
    const preview = server("core/pack_studio/preview.py");
    for (const name of ["RENDER_FAILED", "PREVIEW_INTERRUPTED"]) {
      const value = new RegExp(`^${name} = "([a-z_]+)"$`, "m").exec(
        preview,
      )?.[1];
      if (value) codes.add(value);
    }
    for (const match of server("core/compile/errors.py").matchAll(
      /^ {4}code = "([a-z_]+)"$/gm,
    )) {
      if (match[1]) codes.add(match[1]);
    }
    codes.delete("unknown");
    expect(codes.size).toBeGreaterThan(40);
    const missing = [...codes].filter(
      (code) => !KNOWN_FAILURE_CODES.includes(code),
    );
    expect(missing).toEqual([]);
  });

  it("у каждого семейства сбоев есть заголовок и «что делать» на обоих языках", async () => {
    for (const lng of ["ru", "en"] as const) {
      await setLang(lng);
      for (const family of [
        ...Object.keys(FAILURE_FAMILIES),
        "network",
        "unknown",
      ]) {
        expect(
          tr(`plain.failure.${family}.title`, { defaultValue: "" }),
          `${lng} ${family}`,
        ).not.toBe("");
        expect(
          tr(`plain.failure.${family}.how`, { defaultValue: "" }),
          `${lng} ${family}`,
        ).not.toBe("");
      }
    }
  });
});

describe.each(["ru", "en"] as const)("находки линтера (%s)", (lng) => {
  beforeAll(async () => {
    await setLang(lng);
  });

  it("заголовок и «Как исправить» есть у каждого правила и варианта, подстановки закрыты", () => {
    const naming = makeNaming({ lng, t: tr, ...NAMING_FIXTURE });
    for (const { rule, variant, finding } of FINDING_FIXTURES) {
      const plain = plainFinding(finding, naming, tr);
      const where = `${rule} ${variant}`;
      expect(plain.known, where).toBe(true);
      expect(plain.title, where).not.toBe("");
      expect(plain.how, where).not.toBe("");
      expect(plain.title + plain.how, where).not.toMatch(
        /\{\{|\}\}|plain\.finding/,
      );
      expect(plain.title, where).not.toBe(finding.message);
    }
  });

  it("серверный текст, подсказка, правило, файл и место только в технических подробностях", () => {
    const naming = makeNaming({ lng, t: tr });
    for (const { rule, finding } of FINDING_FIXTURES) {
      const plain = plainFinding(finding, naming, tr);
      const values = plain.tech.map((row) => row.value);
      expect(values, rule).toContain(finding.rule_id);
      expect(values, rule).toContain(finding.message);
      expect(values, rule).toContain(finding.hint);
      if (finding.pointer) expect(values, rule).toContain(finding.pointer);
      if (finding.file) expect(values, rule).toContain(finding.file);
    }
  });

  it("идентификаторы версии не попадают в заголовок и «Как исправить» ни с названиями пака, ни без", () => {
    for (const named of [true, false]) {
      const naming = makeNaming({
        lng,
        t: tr,
        ...(named ? NAMING_FIXTURE : {}),
      });
      for (const { rule, variant, finding } of FINDING_FIXTURES) {
        const plain = plainFinding(finding, naming, tr);
        const visible = `${plain.title} ${plain.how} ${plain.extra ?? ""}`;
        for (const id of FIXTURE_IDS) {
          expect(visible, `${rule} ${variant}: ${id}`).not.toContain(id);
        }
      }
    }
  });

  it("названия из пака подставлены в текст: подпись, документ, точка сдачи", () => {
    const naming = makeNaming({ lng, t: tr, ...NAMING_FIXTURE });
    const text = (rule: string, variant = ""): string => {
      const item = FINDING_FIXTURES.find(
        (fx) => fx.rule === rule && fx.variant === variant,
      );
      if (!item) throw new Error(rule);
      return plainFinding(item.finding, naming, tr).title;
    };
    const pick = (ru: string, en: string): string => (lng === "ru" ? ru : en);
    expect(text("when-never-held")).toContain(
      pick("Консультант / соруководитель", "Consultant"),
    );
    expect(text("when-never-held")).toContain(pick("Отчёт", "Report"));
    expect(text("when-never-held")).toContain(
      pick("Итоговая сдача", "Final submission"),
    );
    expect(text("route-step-without-person")).toContain(
      pick("Согласование темы", "Topic approval"),
    );
    expect(text("route-step-without-person")).toContain(
      pick("Научный руководитель", "Supervisor"),
    );
    expect(text("route-step-without-person")).toContain(
      pick("Академический руководитель", "Academic supervisor"),
    );
    expect(text("variant-lang-outside-langs", "langs")).toContain(
      pick("Заявление на тему", "Topic application"),
    );
    expect(text("variant-lang-outside-langs", "langs")).toContain(
      pick("английский", "English"),
    );
  });

  it("числа и языки: «4 из 12», «3 из 5 комбинаций», пустые подстановки не остаются", () => {
    const naming = makeNaming({ lng, t: tr, ...NAMING_FIXTURE });
    const find = (
      rule: string,
      variant = "",
    ): ReturnType<typeof plainFinding> => {
      const item = FINDING_FIXTURES.find(
        (fx) => fx.rule === rule && fx.variant === variant,
      );
      if (!item) throw new Error(rule);
      return plainFinding(item.finding, naming, tr);
    };
    expect(find("route-step-without-person").extra).toMatch(/4.+12/);
    expect(find("route-gap").extra).toMatch(/3.+12/);
    expect(find("point-empty", "some").title).toMatch(/5.+12/);
    expect(find("atlas-skipped", "numbers").title).toMatch(/30000.+20000/);
    expect(find("translation-missing", "name").title).toContain(
      lng === "ru" ? "английский" : "English",
    );
  });

  it("правило, которого слой не знает: текст сервера как есть и пометка «не известно»", () => {
    const naming = makeNaming({ lng, t: tr });
    const base = FINDING_FIXTURES[0]?.finding;
    if (!base) throw new Error("fixture");
    const plain = plainFinding(
      {
        ...base,
        rule_id: "future-rule",
        message: "Новое правило сервера",
        hint: null,
      },
      naming,
      tr,
    );
    expect(plain.known).toBe(false);
    expect(plain.title).toBe("Новое правило сервера");
    expect(plain.how).not.toBe("");
    expect(plain.tech.map((row) => row.value)).toContain("future-rule");
  });
});

describe.each(["ru", "en"] as const)("сбои сборки (%s)", (lng) => {
  beforeAll(async () => {
    await setLang(lng);
  });

  it("сырой текст Docker только в технических подробностях", () => {
    const plain = plainFailure(
      { code: "docker_unavailable", detail: RAW_DOCKER },
      tr,
    );
    expect(plain.family).toBe("docker");
    expect(plain.title + plain.how).not.toMatch(
      /cannot connect|daemon|docker\.sock/i,
    );
    expect(plain.title).toContain(
      lng === "ru" ? "Docker не запущен" : "Docker is not running",
    );
    expect(plain.tech.map((row) => row.value)).toEqual([
      "docker_unavailable",
      RAW_DOCKER,
    ]);
  });

  it("код из записи сборки главнее ошибки запроса; без кода семейство «неизвестно»", () => {
    expect(
      failureInput(new Error("x"), { code: "image_missing", detail: "d" }),
    ).toEqual({
      code: "image_missing",
      detail: "d",
    });
    expect(failureInput(null, null)).toEqual({ code: null, detail: null });
    expect(familyOf(null)).toBe("unknown");
    expect(familyOf("something_new")).toBe("unknown");
    expect(familyOf("no_runners")).toBe("nobuilder");
    expect(familyOf("whatever", true)).toBe("network");
  });

  it("незнакомый код: общий заголовок, сырой текст сервера в подробностях", () => {
    const plain = plainFailure(
      { code: "something_new", detail: "Raw English text" },
      tr,
    );
    expect(plain.family).toBe("unknown");
    expect(plain.title + plain.how).not.toContain("Raw English text");
    expect(plain.tech.map((row) => row.value)).toContain("Raw English text");
  });
});

describe.each(["ru", "en"] as const)("изменения «Сравнить» (%s)", (lng) => {
  beforeAll(async () => {
    await setLang(lng);
  });

  const find = (kind: string, id?: string) => {
    const item = CHANGE_FIXTURES.find(
      (c) => c.kind === kind && (id === undefined || c.id === id),
    );
    if (!item) throw new Error(kind);
    return item;
  };

  it("роли и шаги называются словами пака, а не идентификаторами", () => {
    const naming = makeNaming({ lng, t: tr, ...NAMING_FIXTURE });
    const pick = (ru: string, en: string): string => (lng === "ru" ? ru : en);
    const person = plainChange(find("participant", "supervisor"), naming, tr);
    expect(person.label).toContain(pick("Научный руководитель", "Supervisor"));
    expect(person.label).not.toMatch(/supervisor|участник /);
    const step = plainChange(find("route_step"), naming, tr);
    expect(step.label).toContain(pick("Согласование темы", "Topic approval"));
    expect(step.label).toContain("2");
    expect(step.before).toBe(
      pick(
        "Научный руководитель, Консультант / соруководитель",
        "Supervisor, Consultant",
      ),
    );
    expect(step.after).toBe(pick("Научный руководитель", "Supervisor"));
    expect(
      plainChange(find("participant", "author2"), naming, tr).label,
    ).toContain(pick("Автор 2", "Author 2"));
  });

  it("сырой вид, внутреннее название и значения сервера лежат в технических подробностях", () => {
    const naming = makeNaming({ lng, t: tr, ...NAMING_FIXTURE });
    const change = find("route_step");
    const plain = plainChange(change, naming, tr);
    const values = plain.tech.map((row) => row.value);
    expect(values).toEqual(
      expect.arrayContaining([
        change.kind,
        change.id,
        change.label,
        "supervisor, co_supervisor",
        "supervisor",
      ]),
    );
  });

  it("значения всех видов разобраны в слова, нераспознанное не выводится сырым", () => {
    const naming = makeNaming({ lng, t: tr, ...NAMING_FIXTURE });
    for (const change of CHANGE_FIXTURES) {
      const plain = plainChange(change, naming, tr);
      for (const side of [plain.before, plain.after]) {
        if (side !== null)
          expect(side, change.kind).not.toMatch(
            /required_at|per_author|applies=|\[|=/,
          );
      }
      if (change.before !== null && change.kind !== "variant") {
        expect(plain.before, change.kind).not.toBeNull();
      }
    }
    const broken = plainChange(
      { ...find("route_pair"), before: "???" },
      makeNaming({ lng, t: tr }),
      tr,
    );
    expect(broken.before).toBeNull();
  });
});

describe("полный прогон по фикстурам", () => {
  it.each(["ru", "en"] as const)(
    "(%s) не пусто и без пустых подстановок",
    async (lng) => {
      await setLang(lng);
      for (const named of [true, false]) {
        const rows = plainTexts(tr, lng, named);
        expect(rows.length).toBeGreaterThan(100);
        for (const row of rows) {
          expect(row.text, row.key).not.toBe("");
          expect(row.text, row.key).not.toMatch(/\{\{|\}\}|undefined|\[object/);
        }
      }
    },
  );

  it("банned: проверка словаря действует (запрещённое слово находится)", () => {
    const hit = (lng: "ru" | "en", text: string): string[] =>
      (banned.server[lng] as { id: string; pattern: string }[])
        .filter((rule) => new RegExp(rule.pattern, "iu").test(text))
        .map((rule) => rule.id);
    expect(hit("ru", "Слот co_supervisor")).toContain("snake-case");
    expect(hit("ru", "Точка topic-approval")).toContain("slug");
    expect(hit("ru", "Поле proposal.stage")).toContain("dot-path");
    expect(hit("ru", "Шаблон body.tex.j2")).toContain("file-name");
    expect(hit("ru", "visible_if")).toContain("manifest-keys");
    expect(hit("ru", "Cannot connect to the Docker daemon")).toContain(
      "docker-raw",
    );
    expect(hit("ru", "в 4 из 12 строк атласа")).toContain("atlas-rows");
    expect(hit("ru", "Научный руководитель: Из компании")).toEqual([]);
    expect(hit("en", "Cannot connect to the Docker daemon")).toContain(
      "docker-raw",
    );
  });
});

describe.each(["ru", "en"] as const)(
  "находки из контрактных фикстур сервера (%s)",
  (lng) => {
    beforeAll(async () => {
      await setLang(lng);
    });
    const dir = join(
      import.meta.dirname,
      "../../../../../../contracts/pack-studio/fixtures/PackOutcomeLint",
    );
    const files = readdirSync(dir).filter((name) => name.endsWith(".json"));

    it("есть что проверять", () => {
      expect(files.length).toBeGreaterThanOrEqual(2);
    });

    it.each(files)("%s: слова без утечек и пустых подстановок", (file) => {
      const data = JSON.parse(readFileSync(join(dir, file), "utf8")) as {
        findings: Parameters<typeof plainFinding>[0][];
      };
      const naming = makeNaming({ lng, t: tr });
      const rules = banned.server[lng];
      expect(data.findings.length).toBeGreaterThan(0);
      for (const finding of data.findings) {
        const plain = plainFinding(finding, naming, tr);
        const visible = `${plain.title} ${plain.how} ${plain.extra ?? ""}`;
        expect(plain.known, finding.rule_id).toBe(true);
        expect(visible, finding.rule_id).not.toMatch(/\{\{|\}\}|undefined/);
        for (const rule of rules) {
          expect(visible, `${finding.rule_id} ${rule.pattern}`).not.toMatch(
            new RegExp(rule.pattern, "iu"),
          );
        }
      }
    });
  },
);
