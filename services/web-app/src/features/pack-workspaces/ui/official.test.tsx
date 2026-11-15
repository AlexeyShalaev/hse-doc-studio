import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { gitRemoteApi } from "@entities/git-remote";
import {
  PackOfficialSchema,
  PackWorkspaceSchema,
  packStudioApi,
  type PackOfficial,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { OfficialPacksCard } from "./OfficialPacks";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const read = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const official = (name: string): PackOfficial =>
  PackOfficialSchema.parse(read("PackOfficial", name));
const WORKSPACE = PackWorkspaceSchema.parse(
  read("PackWorkspace", "git_official"),
);

const credential = (id: string, host: string) => ({
  id,
  kind: "pat",
  label: `Токен ${id}`,
  host,
  status: "ok",
  created_at: "2026-11-15T09:00:00Z",
  used_by: [],
});

const mount = (onOpen = vi.fn()) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <OfficialPacksCard onOpen={onOpen} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onOpen;
};

describe("официальные паки", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("установка без официального репозитория: карточки нет", async () => {
    const info = vi
      .spyOn(packStudioApi, "official")
      .mockResolvedValue(official("hidden"));
    mount();
    await waitFor(() => {
      expect(info).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("official-card")).not.toBeInTheDocument();
  });

  it("пространство уже есть: «Открыть» ведёт в него без окна", async () => {
    const data = official("existing");
    vi.spyOn(packStudioApi, "official").mockResolvedValue(data);
    const onOpen = mount();
    await userEvent.click(await screen.findByTestId("official-open"));
    expect(onOpen).toHaveBeenCalledWith(data.workspace_id);
    expect(screen.queryByTestId("official-dialog")).not.toBeInTheDocument();
  });

  it("свой токен: в списке только доступы хоста репозитория, бота нет", async () => {
    vi.spyOn(packStudioApi, "official").mockResolvedValue(
      official("available"),
    );
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([
      credential("gl", "gitlab.example.org"),
      credential("gh", "github.com"),
    ]);
    const open = vi
      .spyOn(packStudioApi, "openOfficial")
      .mockResolvedValue(WORKSPACE);
    const onOpen = mount();
    await userEvent.click(await screen.findByTestId("official-open"));
    expect(
      await screen.findByTestId("official-access-token"),
    ).toHaveTextContent("ваш форк");
    expect(screen.queryByTestId("official-access-bot")).not.toBeInTheDocument();
    expect(screen.getByTestId("official-dialog")).not.toHaveTextContent(
      "служебный аккаунт",
    );
    await userEvent.click(screen.getByTestId("official-submit"));
    await waitFor(() => {
      expect(open).toHaveBeenCalledWith({ credential_id: "gh" });
    });
    expect(onOpen).toHaveBeenCalledWith(WORKSPACE.id);
  });

  it("нет токена GitHub: объяснение, что нужен токен, отправить нечем", async () => {
    vi.spyOn(packStudioApi, "official").mockResolvedValue(
      official("available"),
    );
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([
      credential("gl", "gitlab.example.org"),
    ]);
    mount();
    await userEvent.click(await screen.findByTestId("official-open"));
    expect(await screen.findByTestId("official-nothing")).toHaveTextContent(
      "нужен токен GitHub",
    );
    expect(screen.getByTestId("official-dialog")).toHaveTextContent(
      "public_repo",
    );
    expect(screen.getByTestId("official-submit")).toBeDisabled();
  });
});
