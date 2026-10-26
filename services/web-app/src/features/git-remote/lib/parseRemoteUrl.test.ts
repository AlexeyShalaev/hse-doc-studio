import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  parseRemoteUrl,
  toHttpsUrl,
  toScpLikeUrl,
  toSshUrl,
  type ParsedRemoteUrl,
  type RemoteUrlPolicy,
} from "./parseRemoteUrl";

// Общие векторы с сервером: тот же файл читает тест parse_remote_url.
type Repeated = {
  prefix: string;
  repeat: string;
  times: number;
  suffix: string;
};
type Case = {
  name: string;
  input: string | Repeated;
  policy?: RemoteUrlPolicy;
  ok: boolean;
  url?: {
    display_url: string;
    kind: string;
    host: string | null;
    provider: string;
    owner: string | null;
    repo: string | null;
    token_stripped: boolean;
  };
  error?: string;
};

const CASES = (
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../../contracts/git-sync/url_cases.json",
      ),
      "utf8",
    ),
  ) as { cases: Case[] }
).cases;

const inputOf = (value: string | Repeated): string =>
  typeof value === "string"
    ? value
    : `${value.prefix}${value.repeat.repeat(value.times)}${value.suffix}`;

describe("parseRemoteUrl: общие векторы контракта", () => {
  it("векторы прочитаны", () => {
    expect(CASES.length).toBeGreaterThan(50);
  });

  it.each(CASES.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const result = parseRemoteUrl(inputOf(c.input), c.policy ?? {});
    if (c.ok) {
      expect(result.ok).toBe(true);
      if (!result.ok) return;
      const { display_url, kind, host, provider, owner, repo, token_stripped } =
        result.url;
      expect({
        display_url,
        kind,
        host,
        provider,
        owner,
        repo,
        token_stripped,
      }).toEqual(c.url);
    } else {
      expect(result).toEqual({ ok: false, error: c.error });
    }
  });
});

const ok = (input: string, policy: RemoteUrlPolicy = {}): ParsedRemoteUrl => {
  const result = parseRemoteUrl(input, policy);
  if (!result.ok)
    throw new Error(`expected ${input} to parse: ${result.error}`);
  return result.url;
};

describe("parseRemoteUrl: подробности", () => {
  it("запоминает порт и пользователя ssh", () => {
    const url = ok("ssh://deploy@git.hse.ru:2222/team/repo.git");
    expect(url.port).toBe(2222);
    expect(url.user).toBe("deploy");
    expect(url.host).toBe("git.hse.ru");
  });

  it("у https нет пользователя, а токен из адреса не попадает в результат", () => {
    const url = ok("https://ghp_SECRET123@github.com/a/b.git");
    expect(url.user).toBeNull();
    expect(url.token_stripped).toBe(true);
    expect(JSON.stringify(url)).not.toContain("SECRET123");
  });

  it("путь хранится без начального слэша", () => {
    expect(ok("git@gitlab.com:group/sub/project.git").path).toBe(
      "group/sub/project.git",
    );
    expect(ok("https://gitlab.com/group/sub/project/").path).toBe(
      "group/sub/project",
    );
  });

  it("репозиторий из одного сегмента не имеет владельца", () => {
    const url = ok("https://git.example.com/solo.git");
    expect(url.owner).toBeNull();
    expect(url.repo).toBe("solo");
  });

  it("папка на компьютере разрешается только политикой", () => {
    expect(parseRemoteUrl("/srv/git/paper.git")).toEqual({
      ok: false,
      error: "url_scheme_forbidden",
    });
    const url = ok("/srv/git/paper.git", { allow_local: true });
    expect(url.kind).toBe("file");
    expect(url.display_url).toBe("file:///srv/git/paper.git");
  });

  it("не принимает букву диска за сервер scp", () => {
    expect(parseRemoteUrl("C:/repo.git", { allow_local: true })).toEqual({
      ok: false,
      error: "url_invalid",
    });
  });

  it("ввод не обязан быть строкой нужной длины: пустое и пробелы это url_invalid", () => {
    expect(parseRemoteUrl("")).toEqual({ ok: false, error: "url_invalid" });
    expect(parseRemoteUrl("\t \n")).toEqual({
      ok: false,
      error: "url_invalid",
    });
  });
});

describe("переписывание адреса между ssh и https", () => {
  it("https в ssh и scp", () => {
    const url = ok("https://github.com/hse-team/paper.git");
    expect(toSshUrl(url)).toBe("ssh://git@github.com/hse-team/paper.git");
    expect(toScpLikeUrl(url)).toBe("git@github.com:hse-team/paper.git");
  });

  it("ssh в https, порт ssh не переносится", () => {
    const url = ok("ssh://git@git.hse.ru:2222/team/paper.git");
    expect(toHttpsUrl(url)).toBe("https://git.hse.ru/team/paper.git");
    // с нестандартным портом scp-запись невозможна: остаётся ssh://
    expect(toScpLikeUrl(url)).toBe("ssh://git@git.hse.ru:2222/team/paper.git");
  });

  it("у папки на компьютере переписывать нечего", () => {
    const url = ok("/srv/git/paper.git", { allow_local: true });
    expect(toSshUrl(url)).toBeNull();
    expect(toHttpsUrl(url)).toBeNull();
    expect(toScpLikeUrl(url)).toBeNull();
  });
});
