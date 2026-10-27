import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { gitRemoteApi, type GitHostSettings } from "@entities/git-remote";
import { parseRemoteUrl, type ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { useInstancePathStore } from "../model/useInstancePathStore";
import { installPointerPolyfills } from "../testing/renderSettings";
import { renderWithClient } from "../testing/renderConnect";
import { ProviderChip } from "./ProviderChip";

const parse = (input: string): ParsedRemoteUrl => {
  const result = parseRemoteUrl(input, { allow_local: true });
  if (!result.ok) throw new Error(result.error);
  return result.url;
};

const settings = (over: Partial<GitHostSettings>): GitHostSettings => ({
  host: "gitlab.hse.local",
  port: null,
  provider_override: null,
  provider_info: { id: "gitlab", detected_by: "host", version: "17.3.1" },
  ca_present: false,
  pinned_fingerprint: null,
  ...over,
});

const setup = (list: GitHostSettings[] = []) => {
  vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue(list);
  return vi
    .spyOn(gitRemoteApi, "updateHostSettings")
    .mockResolvedValue(settings({}));
};

describe("ProviderChip", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    installPointerPolyfills();
    useInstancePathStore.setState({ paths: {} });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("по имени хоста: GitLab, хост и репозиторий", () => {
    setup();
    renderWithClient(
      <ProviderChip url={parse("https://gitlab.com/hse/paper.git")} />,
    );
    const chip = screen.getByTestId("provider-chip");
    expect(chip).toHaveTextContent("GitLab");
    expect(chip).toHaveTextContent("gitlab.com");
    expect(chip).toHaveTextContent("hse/paper");
    expect(chip).toHaveAttribute("data-detected-by", "host");
    expect(screen.queryByTestId("provider-version")).toBeNull();
  });

  it("версия сервера из настроек хоста видна в чипе", async () => {
    setup([settings({})]);
    renderWithClient(
      <ProviderChip url={parse("https://gitlab.hse.local/team/paper.git")} />,
    );
    expect(await screen.findByTestId("provider-version")).toHaveTextContent(
      "v17.3",
    );
  });

  it("версия из ответа проверки адреса", () => {
    setup();
    renderWithClient(
      <ProviderChip
        url={parse("https://gitlab.hse.ru/team/paper.git")}
        known={{ id: "gitlab", detected_by: "host", version: "16.11.2" }}
      />,
    );
    expect(screen.getByTestId("provider-version")).toHaveTextContent("v16.11");
  });

  it("незнакомый сервер: подсказка и выбор типа, выбор запоминается", async () => {
    const update = setup();
    renderWithClient(
      <ProviderChip url={parse("https://git.corp.example/team/paper.git")} />,
    );
    expect(screen.getByTestId("provider-chip")).toHaveTextContent(
      "Другой сервер",
    );
    expect(screen.getByTestId("provider-unknown-hint")).toHaveTextContent(
      "GitLab, GitHub, Gitea или другое",
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("provider-change"));
    const picker = await screen.findByTestId("provider-picker");
    expect(within(picker).getByTestId("provider-option-other")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(within(picker).getByTestId("provider-option-gitlab"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "git.corp.example",
        port: null,
        provider_override: "gitlab",
      });
    });
    await waitFor(() => {
      expect(screen.queryByTestId("provider-picker")).toBeNull();
    });
  });

  it("выбор человека сохранён: чип показывает его, можно вернуть автоопределение", async () => {
    const update = setup([
      settings({
        host: "git.corp.example",
        provider_override: "gitea",
        provider_info: { id: "gitea", detected_by: "override", version: null },
      }),
    ]);
    renderWithClient(
      <ProviderChip url={parse("https://git.corp.example/team/paper.git")} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("provider-chip")).toHaveAttribute(
        "data-detected-by",
        "override",
      );
    });
    expect(screen.getByTestId("provider-chip")).toHaveTextContent("Gitea");
    expect(screen.queryByTestId("provider-unknown-hint")).toBeNull();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("provider-change"));
    await user.click(
      await screen.findByRole("button", { name: "Определять автоматически" }),
    );
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "git.corp.example",
        port: null,
        provider_override: null,
      });
    });
  });

  it("отказ сервера при сохранении выбора показан в окне выбора", async () => {
    const update = setup();
    update.mockRejectedValue(new Error("нет связи"));
    renderWithClient(
      <ProviderChip url={parse("https://git.corp.example/team/paper.git")} />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("provider-change"));
    await user.click(await screen.findByTestId("provider-option-gitea"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Не удалось запомнить выбор|нет связи/,
    );
  });

  it("путь установки запоминается для хоста", async () => {
    setup();
    renderWithClient(
      <ProviderChip url={parse("https://gitlab.hse.ru/team/paper.git")} />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("provider-change"));
    await user.type(await screen.findByLabelText("Путь установки"), "/gitlab/");
    expect(useInstancePathStore.getState().paths["gitlab.hse.ru"]).toBe(
      "gitlab",
    );
  });

  it("папка на компьютере и режим без правки не предлагают выбор", () => {
    setup();
    const { unmount } = renderWithClient(
      <ProviderChip url={parse("/srv/git/paper.git")} />,
    );
    expect(screen.queryByTestId("provider-change")).toBeNull();
    unmount();
    renderWithClient(
      <ProviderChip
        url={parse("https://gitlab.com/hse/paper.git")}
        editable={false}
      />,
    );
    expect(screen.queryByTestId("provider-change")).toBeNull();
  });
});
