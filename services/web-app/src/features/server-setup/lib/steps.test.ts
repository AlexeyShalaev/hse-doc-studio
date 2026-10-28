import { describe, expect, it } from "vitest";
import type { ServerSetupCheck, ServerSetupStatus } from "@entities/session";
import {
  SETUP_STEPS,
  draftIsValid,
  draftToBody,
  environmentVerdict,
  isOccupied,
  nextStep,
  parseDomains,
  prevStep,
  resumeStep,
} from "./steps";

const status = (steps_done: ServerSetupStatus["steps_done"]) =>
  ({ state: "needs_admin", token_required: false, steps_done }) as const;

const check = (
  id: ServerSetupCheck["id"],
  state: ServerSetupCheck["status"],
): ServerSetupCheck => ({ id, status: state, reason: null });

describe("шаги мастера", () => {
  it("идут в порядке: язык, админ, регистрация, входы, окружение, готово", () => {
    expect([...SETUP_STEPS]).toEqual([
      "language",
      "admin",
      "registration",
      "signin",
      "environment",
      "done",
    ]);
    expect(nextStep("language")).toBe("admin");
    expect(nextStep("done")).toBe("done");
    expect(prevStep("admin")).toBe("language");
    expect(prevStep("language")).toBe("language");
  });

  it("после перезагрузки продолжаются с шага, до которого дошёл сервер", () => {
    expect(resumeStep(status([]))).toBe("language");
    expect(resumeStep(status(["admin"]))).toBe("registration");
    expect(resumeStep(status(["admin", "settings"]))).toBe("environment");
  });

  it("занятый мастер: админ есть, а сессии админа нет", () => {
    expect(isOccupied(status(["admin"]), false)).toBe(true);
    expect(isOccupied(status(["admin"]), true)).toBe(false);
    expect(isOccupied(status([]), false)).toBe(false);
  });
});

describe("проверка окружения", () => {
  it("красная обязательная проверка блокирует, необязательная только предупреждает", () => {
    expect(
      environmentVerdict([
        check("database", "ok"),
        check("storage", "fail"),
        check("runner", "not_configured"),
      ]),
    ).toEqual({ blocking: ["storage"], warnings: ["runner"] });
    expect(
      environmentVerdict([
        check("database", "ok"),
        check("storage", "ok"),
        check("runner", "fail"),
      ]),
    ).toEqual({ blocking: [], warnings: ["runner"] });
    expect(
      environmentVerdict([
        check("database", "ok"),
        check("storage", "ok"),
        check("runner", "ok"),
      ]),
    ).toEqual({ blocking: [], warnings: [] });
  });
});

describe("настройки регистрации", () => {
  it("домены разбираются без @, пустых и повторов", () => {
    expect(parseDomains("HSE.ru, @edu.hse.ru;\nhse.ru  ")).toEqual([
      "hse.ru",
      "edu.hse.ru",
    ]);
    expect(parseDomains("  ,; ")).toEqual([]);
  });

  it("режим по доменам без доменов не проходит, в других режимах домены не уходят", () => {
    const draft = {
      registration_mode: "domains" as const,
      domains: "",
      require_approval: false,
      password_enabled: true,
    };
    expect(draftIsValid(draft)).toBe(false);
    expect(draftIsValid({ ...draft, domains: "hse.ru" })).toBe(true);
    expect(
      draftToBody({ ...draft, registration_mode: "invite", domains: "hse.ru" })
        .registration_domains,
    ).toEqual([]);
  });
});
