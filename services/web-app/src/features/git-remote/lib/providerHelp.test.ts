import { describe, expect, it } from "vitest";
import { parseRemoteUrl, type ParsedRemoteUrl } from "./parseRemoteUrl";
import {
  KEY_STEPS,
  TOKEN_STEPS,
  defaultCredentialLabel,
  deployKeyUrl,
  repoWebUrl,
  tokenCreateUrl,
} from "./providerHelp";

const parse = (input: string): ParsedRemoteUrl => {
  const result = parseRemoteUrl(input, { allow_local: true });
  if (!result.ok) throw new Error(result.error);
  return result.url;
};

describe("ссылки на страницы сервера", () => {
  it("github: токен и ключ репозитория", () => {
    const url = parse("git@github.com:hse-team/paper.git");
    expect(tokenCreateUrl(url)).toBe(
      "https://github.com/settings/personal-access-tokens/new",
    );
    expect(deployKeyUrl(url)).toBe(
      "https://github.com/hse-team/paper/settings/keys/new",
    );
    expect(repoWebUrl(url)).toBe("https://github.com/hse-team/paper");
  });

  it("gitlab: вложенные группы остаются в пути, токен просит write_repository", () => {
    const url = parse("https://gitlab.com/group/sub/paper.git");
    expect(tokenCreateUrl(url)).toContain("scopes=write_repository");
    expect(deployKeyUrl(url)).toBe(
      "https://gitlab.com/group/sub/paper/-/settings/repository",
    );
  });

  it("свой сервер gitlab с портом https берёт его в ссылку", () => {
    const url = parse("https://gitlab.hse.ru:8443/team/paper.git");
    expect(tokenCreateUrl(url)).toMatch(/^https:\/\/gitlab\.hse\.ru:8443\//);
  });

  it("порт ssh не попадает в адрес сайта", () => {
    const url = parse("ssh://git@gitlab.hse.ru:2222/team/paper.git");
    expect(repoWebUrl(url)).toBe("https://gitlab.hse.ru/team/paper");
    expect(deployKeyUrl(url)).toBe(
      "https://gitlab.hse.ru/team/paper/-/settings/repository",
    );
  });

  it("gitea, bitbucket", () => {
    expect(deployKeyUrl(parse("https://codeberg.org/anna/paper.git"))).toBe(
      "https://codeberg.org/anna/paper/settings/keys",
    );
    expect(tokenCreateUrl(parse("https://bitbucket.org/anna/paper.git"))).toBe(
      "https://bitbucket.org/account/settings/app-passwords/",
    );
  });

  it("у незнакомого сервера и у папки ссылок нет", () => {
    const other = parse("https://git.example.com/team/paper.git");
    expect(tokenCreateUrl(other)).toBeNull();
    expect(deployKeyUrl(other)).toBeNull();
    const file = parse("/srv/git/paper.git");
    expect(repoWebUrl(file)).toBeNull();
    expect(tokenCreateUrl(file)).toBeNull();
  });
});

describe("инструкции", () => {
  it("у каждого провайдера есть шаги для токена и для ключа", () => {
    for (const steps of [TOKEN_STEPS, KEY_STEPS]) {
      for (const list of Object.values(steps)) {
        expect(list.length).toBeGreaterThan(0);
      }
    }
  });

  it("имя доступа по умолчанию", () => {
    expect(defaultCredentialLabel("GitHub", "github.com")).toBe(
      "GitHub, github.com",
    );
    expect(defaultCredentialLabel("git.hse.ru", "git.hse.ru")).toBe(
      "git.hse.ru",
    );
  });
});
