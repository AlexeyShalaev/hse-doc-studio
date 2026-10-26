import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  PROFILE_EMAIL_MAX,
  PROFILE_NAME_MAX,
  formatCommitAuthor,
  isProfileIssueCode,
  normalizeEmail,
  normalizeName,
  validateEmail,
  validateName,
  validateProfile,
} from "./validateProfile";

type Repeated = {
  prefix: string;
  repeat: string;
  times: number;
  suffix: string;
};
type Raw = string | Repeated;
type Case = {
  name: string;
  input: Raw;
  ok: boolean;
  normalized?: Raw;
  code?: string;
};

const CASES = JSON.parse(
  readFileSync(
    join(
      import.meta.dirname,
      "../../../../../../contracts/git-sync/profile_cases.json",
    ),
    "utf8",
  ),
) as { name: Case[]; email: Case[] };

const expand = (raw: Raw): string =>
  typeof raw === "string"
    ? raw
    : `${raw.prefix}${raw.repeat.repeat(raw.times)}${raw.suffix}`;

describe("validateProfile: общие векторы с сервером", () => {
  it("векторы не пусты и имена в каждом списке уникальны", () => {
    for (const list of [CASES.name, CASES.email]) {
      expect(list.length).toBeGreaterThan(10);
      const names = list.map((c) => c.name);
      expect(new Set(names).size).toBe(names.length);
    }
  });

  it.each(CASES.name.map((c) => [c.name, c] as const))(
    "имя: %s",
    (_label, c) => {
      const input = expand(c.input);
      if (c.ok) {
        expect(validateName(input)).toBeNull();
        expect(normalizeName(input)).toBe(expand(c.normalized ?? ""));
      } else {
        expect(validateName(input)).toBe(c.code);
      }
    },
  );

  it.each(CASES.email.map((c) => [c.name, c] as const))(
    "e-mail: %s",
    (_label, c) => {
      const input = expand(c.input);
      if (c.ok) {
        expect(validateEmail(input)).toBeNull();
        expect(normalizeEmail(input)).toBe(expand(c.normalized ?? ""));
      } else {
        expect(validateEmail(input)).toBe(c.code);
      }
    },
  );

  it("коды векторов входят в закрытый список", () => {
    for (const c of [...CASES.name, ...CASES.email]) {
      if (c.code) expect(isProfileIssueCode(c.code)).toBe(true);
    }
  });
});

describe("validateProfile", () => {
  it("лимиты совпадают с серверными", () => {
    expect(PROFILE_NAME_MAX).toBe(128);
    expect(PROFILE_EMAIL_MAX).toBe(254);
  });

  it("собирает ошибки по полям и нормализованные значения", () => {
    const bad = validateProfile({ name: "  ", email: "x" });
    expect(bad.isValid).toBe(false);
    expect(bad.issues).toEqual({
      name: "name_required",
      email: "email_invalid",
    });

    const good = validateProfile({
      name: "  Иван   Смирнов ",
      email: " Ivan@EDU.hse.ru ",
    });
    expect(good).toEqual({
      name: "Иван Смирнов",
      email: "Ivan@edu.hse.ru",
      issues: {},
      isValid: true,
    });
  });

  it("не знает кодов, которых нет в списке", () => {
    expect(isProfileIssueCode("email_invalid")).toBe(true);
    expect(isProfileIssueCode("bad_format")).toBe(false);
  });
});

describe("formatCommitAuthor", () => {
  it("склеивает имя и почту и не выдумывает недостающее", () => {
    expect(formatCommitAuthor("Иван", "i@b.ru")).toBe("Иван <i@b.ru>");
    expect(formatCommitAuthor("Иван", "")).toBe("Иван");
    expect(formatCommitAuthor("", "i@b.ru")).toBe("<i@b.ru>");
    expect(formatCommitAuthor("", "")).toBe("");
  });
});
