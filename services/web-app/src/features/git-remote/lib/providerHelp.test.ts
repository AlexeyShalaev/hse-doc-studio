import { describe, expect, it } from "vitest";
import { parseRemoteUrl, type ParsedRemoteUrl } from "./parseRemoteUrl";
import {
  KEY_STEPS,
  TOKEN_STEPS,
  USER_KEY_STEPS,
  defaultCredentialLabel,
  deployKeyUrl,
  repoWebUrl,
  sshLinksFor,
  tokenCreateUrl,
  tokenLinksFor,
} from "./providerHelp";

const parse = (input: string): ParsedRemoteUrl => {
  const result = parseRemoteUrl(input, { allow_local: true });
  if (!result.ok) throw new Error(result.error);
  return result.url;
};

const CONTEXT = {
  projectName: "Курсовая работа",
  lang: "ru",
  today: "2026-10-27",
};

describe("ссылки на страницы сервера", () => {
  it("github: точный токен с подстановкой, классический как запасной, deploy-ключ", () => {
    const url = parse("git@github.com:hse-team/paper.git");
    const links = tokenLinksFor(url, CONTEXT);
    const primary = new URL(links?.primary?.url ?? "");
    expect(primary.origin + primary.pathname).toBe(
      "https://github.com/settings/personal-access-tokens/new",
    );
    expect(primary.searchParams.get("name")).toBe(
      "HSE Studio · Курсовая работа",
    );
    expect(primary.searchParams.get("target_name")).toBe("hse-team");
    expect(primary.searchParams.get("expires_in")).toBe("90");
    expect(primary.searchParams.get("contents")).toBe("write");
    expect(links?.fallback).toMatchObject({ broad: true });
    expect(links?.fallback?.url).toContain("scopes=repo");
    expect(deployKeyUrl(url)).toBe(
      "https://github.com/hse-team/paper/settings/keys/new",
    );
    expect(repoWebUrl(url)).toBe("https://github.com/hse-team/paper");
  });

  it("gitlab: вложенные группы остаются в пути, токен просит чтение и запись без api", () => {
    const url = parse("https://gitlab.com/group/sub/paper.git");
    const primary = new URL(tokenCreateUrl(url, CONTEXT) ?? "");
    expect(primary.pathname).toBe("/-/user_settings/personal_access_tokens");
    expect(primary.searchParams.get("scopes")).toBe(
      "read_repository,write_repository",
    );
    expect(primary.searchParams.get("description")).toBe(
      "Доступ для HSE Doc Studio, 2026-10-27",
    );
    const fallback = tokenLinksFor(url, CONTEXT)?.fallback;
    expect(new URL(fallback?.url ?? "").pathname).toBe(
      "/-/profile/personal_access_tokens",
    );
    expect(deployKeyUrl(url)).toBe(
      "https://gitlab.com/group/sub/paper/-/settings/repository",
    );
  });

  it("свой сервер gitlab берёт порт https и путь установки в ссылки", () => {
    const url = parse("https://gitlab.hse.ru:8443/team/paper.git");
    expect(tokenCreateUrl(url, CONTEXT)).toMatch(
      /^https:\/\/gitlab\.hse\.ru:8443\/-\/user_settings\//,
    );
    expect(tokenCreateUrl(url, { ...CONTEXT, subpath: "/gitlab" })).toMatch(
      /^https:\/\/gitlab\.hse\.ru:8443\/gitlab\/-\/user_settings\//,
    );
    expect(sshLinksFor(url, { subpath: "gitlab" })?.userKeys?.url).toBe(
      "https://gitlab.hse.ru:8443/gitlab/-/user_settings/ssh_keys",
    );
  });

  it("порт ssh не попадает в адрес сайта", () => {
    const url = parse("ssh://git@gitlab.hse.ru:2222/team/paper.git");
    expect(repoWebUrl(url)).toBe("https://gitlab.hse.ru/team/paper");
    expect(deployKeyUrl(url)).toBe(
      "https://gitlab.hse.ru/team/paper/-/settings/repository",
    );
  });

  it("выбранный человеком провайдер сильнее догадки по адресу", () => {
    const url = parse("https://git.example.com/team/paper.git");
    expect(tokenCreateUrl(url, CONTEXT)).toBeNull();
    expect(tokenCreateUrl(url, { ...CONTEXT, provider: "gitlab" })).toContain(
      "/-/user_settings/personal_access_tokens",
    );
  });

  it("gitea и bitbucket: простые ссылки без подстановки", () => {
    const gitea = parse("https://codeberg.org/anna/paper.git");
    const links = tokenLinksFor(gitea, CONTEXT);
    expect(links?.primary).toMatchObject({
      kind: "plain",
      url: "https://codeberg.org/user/settings/applications",
    });
    expect(links?.fallback).toBeNull();
    expect(deployKeyUrl(gitea)).toBe(
      "https://codeberg.org/anna/paper/settings/keys",
    );
    expect(tokenCreateUrl(parse("https://bitbucket.org/anna/paper.git"))).toBe(
      "https://bitbucket.org/anna/paper/admin/access-tokens",
    );
  });

  it("у незнакомого сервера и у папки ссылок на токен нет", () => {
    const other = parse("https://git.example.com/team/paper.git");
    expect(tokenCreateUrl(other)).toBeNull();
    expect(deployKeyUrl(other)).toBeNull();
    const file = parse("/srv/git/paper.git");
    expect(repoWebUrl(file)).toBeNull();
    expect(tokenCreateUrl(file)).toBeNull();
    expect(tokenLinksFor(file)).toBeNull();
  });

  it("длинное название проекта укорачивается до лимита GitHub", () => {
    const url = parse("https://github.com/hse/paper.git");
    const link = new URL(
      tokenCreateUrl(url, { ...CONTEXT, projectName: "Д".repeat(120) }) ?? "",
    );
    expect(
      Array.from(link.searchParams.get("name") ?? "").length,
    ).toBeLessThanOrEqual(40);
  });
});

describe("инструкции", () => {
  it("у каждого провайдера есть шаги для токена и для ключей", () => {
    for (const steps of [TOKEN_STEPS, KEY_STEPS, USER_KEY_STEPS]) {
      for (const [provider, list] of Object.entries(steps)) {
        // Сервер Студии выдаёт доступ входом по коду устройства, а не токеном или ключом.
        if (provider === "hse_studio") expect(list).toEqual([]);
        else expect(list.length).toBeGreaterThan(0);
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
