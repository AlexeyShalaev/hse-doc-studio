import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackCiStatusSchema,
  PackGitSchema,
  PackOfficialSchema,
  PackProposeResponseSchema,
  PackWorkspaceSchema,
  ciPollInterval,
  CI_APPROVAL_POLL_MS,
  packStudioApi,
  type PackGit,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackGitBar } from "./PackGitBar";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const DIRTY = fixture(PackGitSchema, "PackGit", "detached_dirty");
const OFFICIAL_WS = fixture(
  PackWorkspaceSchema,
  "PackWorkspace",
  "git_official_bot",
);
const OFFICIAL = fixture(PackOfficialSchema, "PackOfficial", "bot_available");
const APPROVAL = fixture(
  PackCiStatusSchema,
  "PackCiStatus",
  "github_awaiting_approval",
);
const MERGED = fixture(PackCiStatusSchema, "PackCiStatus", "github_merged");
const PR = fixture(
  PackProposeResponseSchema,
  "PackProposeResponse",
  "github_pr",
);

/** Официальное пространство с ботом: правки есть, согласия ещё нет. */
const officialGit = (patch: Partial<PackGit["workspace"]> = {}): PackGit => ({
  ...DIRTY,
  workspace: {
    ...OFFICIAL_WS,
    pushed_sha: null,
    pr_url: null,
    pr_number: null,
    ci_status: null,
    license_accepted_at: null,
    ...patch,
  },
});

const mount = (git: PackGit) => {
  vi.spyOn(packStudioApi, "git").mockResolvedValue(git);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PackGitBar
          workspace={git.workspace}
          editorDirty={false}
          onOpenFile={vi.fn()}
          onLintFailed={vi.fn()}
          onFilesChanged={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("официальные паки в панели git", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("первая отправка через бота: согласие с лицензией обязательно, остаток лимита виден", async () => {
    vi.spyOn(packStudioApi, "official").mockResolvedValue(OFFICIAL);
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount(officialGit());
    await userEvent.click(await screen.findByTestId("propose-changes"));

    expect(await screen.findByTestId("git-propose-bot")).toHaveTextContent(
      "Сегодня можно ещё 4 из 5 предложений.",
    );
    expect(await screen.findByTestId("git-propose-license")).toHaveTextContent(
      "Apache-2.0",
    );
    expect(screen.getByText("Лицензия")).toHaveAttribute(
      "href",
      OFFICIAL.repo?.license_url,
    );
    expect(screen.getByText("Правила вклада")).toHaveAttribute(
      "href",
      OFFICIAL.repo?.contributing_url,
    );
    const submit = screen.getByTestId("git-propose-submit");
    expect(submit).toBeDisabled();

    await userEvent.click(screen.getByTestId("git-propose-license-accept"));
    await userEvent.click(submit);
    await waitFor(() => {
      expect(propose).toHaveBeenCalledWith(
        OFFICIAL_WS.id,
        expect.objectContaining({ accept_license: true }),
      );
    });
  });

  it("согласие уже дано: галочки нет, отправка без accept_license", async () => {
    vi.spyOn(packStudioApi, "official").mockResolvedValue(OFFICIAL);
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount(officialGit({ license_accepted_at: "2026-11-15T10:05:00Z" }));
    await userEvent.click(await screen.findByTestId("propose-changes"));
    await screen.findByTestId("git-propose-bot");
    expect(screen.queryByTestId("git-propose-license")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    await waitFor(() => {
      expect(propose).toHaveBeenCalled();
    });
    expect(propose.mock.calls[0]?.[1]).not.toHaveProperty("accept_license");
  });

  it("проверки ждут одобрения сопровождающего: сказано словами, опрос реже", async () => {
    vi.spyOn(packStudioApi, "checks").mockResolvedValue(APPROVAL);
    mount(officialGit({ pushed_sha: APPROVAL.sha }));
    const badge = await screen.findByTestId("git-ci");
    await waitFor(() => {
      expect(badge).toHaveAttribute("data-state", "awaiting_approval");
    });
    expect(badge).toHaveTextContent("Ждут одобрения");
    await userEvent.click(badge);
    expect(await screen.findByTestId("git-ci-approval")).toHaveTextContent(
      "сопровождающий",
    );
    expect(ciPollInterval(APPROVAL)).toBe(CI_APPROVAL_POLL_MS);
  });

  it("PR слит: официальные паки выйдут со следующим выпуском, опрос остановлен", async () => {
    vi.spyOn(packStudioApi, "checks").mockResolvedValue(MERGED);
    mount(officialGit({ pushed_sha: MERGED.sha, pr_number: 412 }));
    expect(await screen.findByTestId("git-pr-merged")).toHaveTextContent(
      "со следующим выпуском Студии",
    );
    expect(ciPollInterval(MERGED)).toBe(false);
  });
});
