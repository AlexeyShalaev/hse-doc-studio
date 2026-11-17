import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  PackGitSchema,
  PackProposeResponseSchema,
  packOutcomeApi,
  packStudioApi,
  type PackGit,
} from "@entities/pack-studio";
import {
  referenceImpact,
  type ModesBehavior,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { ProposeDialog } from "./ProposeDialog";

// «Предложить изменения» с блоком «до и после» (F10): отметка «я знаю», описание PR, gate.

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const read = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const DIRTY = PackGitSchema.parse(read("PackGit", "detached_dirty"));
const PR = PackProposeResponseSchema.parse(
  read("PackProposeResponse", "github_pr"),
);

const impactReply = (behavior: ModesBehavior) => ({
  data: referenceImpact(behavior),
  etag: null,
});

const mount = (git: PackGit = DIRTY, onLintFailed = vi.fn()) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = (isOpen: boolean) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProposeDialog
          git={git}
          isOpen={isOpen}
          onClose={vi.fn()}
          editorDirty={false}
          onLintFailed={onLintFailed}
          onAccess={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const { rerender } = render(view(false));
  return {
    open: () => {
      rerender(view(true));
    },
  };
};

describe("«Предложить изменения»: до и после (F10)", () => {
  beforeAll(async () => {
    await Promise.all([loadPackStudioNamespace(), loadPackOutcomeNamespace()]);
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  const treeSpy = () =>
    vi.spyOn(packStudioApi, "tree").mockResolvedValue({
      workspace_id: "w",
      base_sha: null,
      packs: [],
      files: [],
      truncated: false,
    });

  it("пока диалог закрыт, расчёт не идёт", async () => {
    treeSpy();
    const impact = vi
      .spyOn(packOutcomeApi, "impact")
      .mockResolvedValue(impactReply("normal"));
    mount();
    await new Promise((r) => setTimeout(r, 50));
    expect(impact).not.toHaveBeenCalled();
  });

  it("изменился сценарий: кнопка «Предложить всё равно» неактивна до отметки, в описание идёт сводка", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(impactReply("normal"));
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount().open();
    const submit = await screen.findByTestId("git-propose-submit");
    expect(await screen.findByTestId("impact-headline")).toHaveTextContent(
      "Изменится результат в 1 из 3 сценариев",
    );
    await waitFor(() => {
      expect(submit).toHaveTextContent("Предложить всё равно");
    });
    expect(submit).toBeDisabled();
    const ack = await screen.findByTestId("git-propose-ack-input");
    await userEvent.click(ack);
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => {
      expect(propose).toHaveBeenCalled();
    });
    const body = propose.mock.calls[0]?.[1];
    expect(body?.description).toContain(
      "Изменится результат в 1 из 3 сценариев",
    );
    expect(body?.description).toContain("### Что изменится в результате");
  });

  it("сводку можно не добавлять в описание", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(impactReply("normal"));
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount().open();
    await userEvent.click(await screen.findByTestId("git-propose-ack-input"));
    await userEvent.click(
      await screen.findByTestId("git-propose-summary-input"),
    );
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    await waitFor(() => {
      expect(propose).toHaveBeenCalled();
    });
    expect(propose.mock.calls[0]?.[1].description).toBeNull();
  });

  it("без изменений: обычная кнопка, без отметки, описание не меняется", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(
      impactReply("impact_same"),
    );
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount().open();
    const submit = screen.getByTestId("git-propose-submit");
    await waitFor(() => {
      expect(submit).toBeEnabled();
    });
    expect(submit).toHaveTextContent("Отправить и открыть PR");
    expect(screen.queryByTestId("git-propose-ack")).toBeNull();
    await userEvent.click(submit);
    await waitFor(() => {
      expect(propose).toHaveBeenCalled();
    });
    expect(propose.mock.calls[0]?.[1].description).toBeNull();
  });

  it("упавший сценарий тоже требует отметки", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(
      impactReply("impact_error"),
    );
    mount().open();
    expect(await screen.findByTestId("git-propose-ack")).toBeInTheDocument();
    expect(screen.getByTestId("git-propose-submit")).toBeDisabled();
  });

  it("пока считается, отправка ждёт; отмена расчёта открывает её без отметки", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockImplementation(
      () => new Promise(() => undefined),
    );
    mount().open();
    const submit = screen.getByTestId("git-propose-submit");
    expect(
      await screen.findByTestId("git-propose-impact-waiting"),
    ).toBeInTheDocument();
    expect(submit).toBeDisabled();
    await userEvent.click(await screen.findByTestId("impact-cancel"));
    await waitFor(() => {
      expect(submit).toBeEnabled();
    });
    expect(screen.queryByTestId("git-propose-ack")).toBeNull();
  });

  it("ошибка расчёта и нет базы не блокируют отправку", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockRejectedValue(
      new ApiError("x", "diff_base_unavailable", 409, {
        reason: "new_version",
      }),
    );
    mount().open();
    expect(
      await screen.findByTestId("impact-no-base-new_version"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("git-propose-submit")).toBeEnabled();
    });
  });

  it("gate: находки проверок пака по-прежнему уходят в onLintFailed", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(
      impactReply("impact_same"),
    );
    vi.spyOn(packStudioApi, "propose").mockRejectedValue(
      new ApiError("lint", "lint_failed", 422, {
        errors: 1,
        warnings: 0,
        findings: [],
      }),
    );
    const onLintFailed = vi.fn();
    mount(DIRTY, onLintFailed).open();
    const submit = screen.getByTestId("git-propose-submit");
    await waitFor(() => {
      expect(submit).toBeEnabled();
    });
    await userEvent.click(submit);
    await waitFor(() => {
      expect(onLintFailed).toHaveBeenCalled();
    });
  });

  it("без правок в версиях блока нет, отправка как раньше", () => {
    treeSpy();
    const impact = vi.spyOn(packOutcomeApi, "impact");
    mount({
      ...DIRTY,
      changed: [{ path: "hse-cs-sse/pack.yaml", status: "modified" }],
    }).open();
    expect(screen.queryByTestId("impact-block")).toBeNull();
    expect(screen.getByTestId("git-propose-submit")).toBeEnabled();
    expect(impact).not.toHaveBeenCalled();
  });

  it("клавиатура: отметка ставится пробелом и открывает кнопку", async () => {
    treeSpy();
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(impactReply("normal"));
    mount().open();
    const ack = await screen.findByTestId("git-propose-ack-input");
    ack.focus();
    await userEvent.keyboard(" ");
    expect(ack).toBeChecked();
    expect(screen.getByTestId("git-propose-submit")).toBeEnabled();
  });
});
