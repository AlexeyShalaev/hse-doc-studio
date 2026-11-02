import { describe, expect, it } from "vitest";
import type { OnboardingState } from "@entities/onboarding";
import { decidePrompt } from "./autostart";
import { resolveBuildAvailability } from "./buildAvailability";
import { suggestTemplate, workOptions } from "./templateSuggestion";
import { SCENARIO_VERSION } from "../model/scenario";

const state = (patch: Partial<OnboardingState>): OnboardingState => ({
  status: "pending",
  scenario_version: 0,
  step: null,
  answers: {},
  started_at: null,
  finished_at: null,
  updated_at: null,
  ...patch,
});
const HOME = { pathname: "/", automated: false, flag: null };

describe("когда показывать онбординг", () => {
  it("новичку на главной тур открывается сам", () => {
    expect(decidePrompt(state({}), HOME, false)).toBe("autostart");
  });

  it("не на главной и до ответа сервера ничего", () => {
    expect(
      decidePrompt(state({}), { ...HOME, pathname: "/settings" }, false),
    ).toBe("none");
    expect(decidePrompt(undefined, HOME, false)).toBe("none");
  });

  it("под автоматизацией молчит, пока флаг не включит", () => {
    const robot = { ...HOME, automated: true };
    expect(decidePrompt(state({}), robot, false)).toBe("none");
    expect(decidePrompt(state({}), { ...robot, flag: "on" }, false)).toBe(
      "autostart",
    );
    expect(decidePrompt(state({}), { ...HOME, flag: "off" }, false)).toBe(
      "none",
    );
  });

  it("давнему пользователю приглашение, закрытое не возвращается", () => {
    expect(decidePrompt(state({ status: "suggested" }), HOME, false)).toBe(
      "invite",
    );
    expect(decidePrompt(state({ status: "suggested" }), HOME, true)).toBe(
      "none",
    );
    expect(decidePrompt(state({ status: "in_progress" }), HOME, false)).toBe(
      "invite",
    );
  });

  it("пройденный тур молчит, пока сценарий не обновился", () => {
    expect(
      decidePrompt(
        state({ status: "completed", scenario_version: SCENARIO_VERSION }),
        HOME,
        false,
      ),
    ).toBe("none");
    expect(
      decidePrompt(
        state({ status: "completed", scenario_version: SCENARIO_VERSION - 1 }),
        HOME,
        false,
      ),
    ).toBe("invite");
    expect(decidePrompt(state({ status: "skipped" }), HOME, false)).toBe(
      "none",
    );
  });
});

const PACKS = [
  {
    id: "hse-cs-se",
    name: { ru: "ПИ бакалавриат", en: "SE bachelor" },
    templates: [
      { id: "vkr", name: { ru: "ВКР", en: "Thesis" } },
      { id: "coursework", name: { ru: "Курсовая", en: "Coursework" } },
    ],
  },
];

describe("шаблон из ответов", () => {
  it("варианты работы строятся из каталога", () => {
    expect(workOptions(PACKS, "en")).toEqual([
      { value: "hse-cs-se/vkr", label: "Thesis · SE bachelor" },
      { value: "hse-cs-se/coursework", label: "Coursework · SE bachelor" },
    ]);
  });

  it("выбранный шаблон, иначе курсовая, пустой каталог даёт null", () => {
    expect(
      suggestTemplate(PACKS, { work: "hse-cs-se/vkr" }, "ru")?.templateId,
    ).toBe("vkr");
    expect(suggestTemplate(PACKS, { work: "other" }, "ru")?.templateId).toBe(
      "coursework",
    );
    expect(suggestTemplate([], {}, "ru")).toBeNull();
  });
});

describe("доступность сборки", () => {
  const runners = (any: boolean, tags: string[]) => ({
    cloud: true,
    any_runner: any,
    tags,
  });

  it("локально Docker, на сервере по живым раннерам или «неизвестно»", () => {
    expect(resolveBuildAvailability("local")).toBe("local");
    expect(resolveBuildAvailability("server")).toBe("unknown");
    expect(resolveBuildAvailability("server", runners(true, ["tex"]))).toBe(
      "available",
    );
    expect(resolveBuildAvailability("server", runners(false, []))).toBe(
      "unavailable",
    );
  });

  it("раннер без TeX сборку PDF не берёт", () => {
    expect(resolveBuildAvailability("server", runners(true, ["office"]))).toBe(
      "unavailable",
    );
  });

  it("ответ «не облако» значит локальная сборка", () => {
    expect(
      resolveBuildAvailability("server", {
        cloud: false,
        any_runner: true,
        tags: [],
      }),
    ).toBe("local");
  });
});
