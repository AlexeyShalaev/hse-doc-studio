import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { parseRemoteUrl, type ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { TokenLinkCard } from "./TokenLinkCard";

const parse = (input: string, provider?: ParsedRemoteUrl["provider"]) => {
  const result = parseRemoteUrl(input);
  if (!result.ok) throw new Error(result.error);
  return provider ? { ...result.url, provider } : result.url;
};

const hrefOf = (name: RegExp): URL =>
  new URL(screen.getByRole("link", { name }).getAttribute("href") ?? "");

describe("TokenLinkCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("gitlab.com: кнопка ведёт на страницу с названием, описанием и правами", () => {
    render(
      <TokenLinkCard
        url={parse("https://gitlab.com/hse/paper.git")}
        projectName="Курсовая работа"
      />,
    );
    const link = screen.getByTestId("token-create-link");
    expect(link).toHaveTextContent("Создать токен на GitLab");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    const url = new URL(link.getAttribute("href") ?? "");
    expect(url.pathname).toBe("/-/user_settings/personal_access_tokens");
    expect(url.searchParams.get("name")).toBe("HSE Studio · Курсовая работа");
    expect(url.searchParams.get("scopes")).toBe(
      "read_repository,write_repository",
    );
    // Права названы, api не просится.
    const steps = screen.getByTestId("token-helper-steps");
    expect(within(steps).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByTestId("token-link-card")).toHaveTextContent("без api");
    expect(screen.getByTestId("token-fallback")).toHaveTextContent(
      "Открыть страницу для старых версий",
    );
    expect(screen.queryByTestId("gitlab-legacy-note")).toBeNull();
  });

  it("старый GitLab: главной становится ссылка для старых версий", () => {
    render(
      <TokenLinkCard
        url={parse("https://gitlab.old.hse.ru/team/paper.git")}
        serverVersion="13.12.2"
      />,
    );
    expect(screen.getByTestId("gitlab-legacy-note")).toHaveTextContent(
      "GitLab 13.12.2",
    );
    expect(
      new URL(
        screen.getByTestId("token-create-link").getAttribute("href") ?? "",
      ).pathname,
    ).toBe("/-/profile/personal_access_tokens");
    expect(hrefOf(/Открыть страницу для новых версий/).pathname).toBe(
      "/-/user_settings/personal_access_tokens",
    );
  });

  it("новый GitLab не считается старым", () => {
    render(
      <TokenLinkCard
        url={parse("https://gitlab.hse.ru/team/paper.git")}
        serverVersion="17.3.1"
      />,
    );
    expect(screen.queryByTestId("gitlab-legacy-note")).toBeNull();
  });

  it("github: напоминание выбрать репозиторий и запасной классический токен с предупреждением", () => {
    render(<TokenLinkCard url={parse("https://github.com/hse/paper.git")} />);
    expect(screen.getByTestId("github-repo-note")).toHaveTextContent(
      "Only select repositories",
    );
    const url = new URL(
      screen.getByTestId("token-create-link").getAttribute("href") ?? "",
    );
    expect(url.pathname).toBe("/settings/personal-access-tokens/new");
    expect(url.searchParams.get("target_name")).toBe("hse");
    expect(screen.getByTestId("token-broad-warning")).toHaveTextContent(
      "доступ ко всем твоим репозиториям",
    );
    expect(hrefOf(/Классический токен/).searchParams.get("scopes")).toBe(
      "repo",
    );
  });

  it("gitea: ссылка без подстановки и шаги по номерам, раскрытые сразу", () => {
    render(
      <TokenLinkCard url={parse("https://codeberg.org/anna/paper.git")} />,
    );
    const link = screen.getByTestId("token-create-link");
    expect(link).toHaveTextContent("Открыть страницу токенов Gitea");
    expect(link.getAttribute("href")).toBe(
      "https://codeberg.org/user/settings/applications",
    );
    expect(screen.getByText(/не принимает подстановку/)).toBeInTheDocument();
    expect(screen.queryByTestId("token-fallback")).toBeNull();
    const details = screen.getByText("Подробные шаги").closest("details");
    expect(details).toHaveAttribute("open");
  });

  it("неизвестный сервер: кнопки нет, только шаги", () => {
    render(<TokenLinkCard url={parse("https://git.example.com/a/b.git")} />);
    expect(screen.queryByTestId("token-create-link")).toBeNull();
    expect(screen.getByText(/персональный токен доступа/)).toBeInTheDocument();
  });

  it("выбранный провайдер сильнее адреса", () => {
    render(
      <TokenLinkCard
        url={parse("https://git.example.com/a/b.git", "gitlab")}
      />,
    );
    expect(screen.getByTestId("token-create-link")).toHaveTextContent(
      "Создать токен на GitLab",
    );
  });

  it("английский язык", async () => {
    await i18n.changeLanguage("en");
    render(<TokenLinkCard url={parse("https://gitlab.com/hse/paper.git")} />);
    expect(screen.getByTestId("token-create-link")).toHaveTextContent(
      "Create a token on GitLab",
    );
    const description = new URL(
      screen.getByTestId("token-create-link").getAttribute("href") ?? "",
    ).searchParams.get("description");
    expect(description).toMatch(
      /^Access for HSE Doc Studio, \d{4}-\d{2}-\d{2}$/,
    );
  });
});
