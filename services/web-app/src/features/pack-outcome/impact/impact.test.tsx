import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  packOutcomeApi,
  packStudioApi,
  type PackTree,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  referenceImpact,
  type ModesBehavior,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { ImpactBlock, type ImpactReport } from "./ImpactBlock";

const REF: PackVersionRef = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};
const tree = (released: boolean): PackTree => ({
  workspace_id: "ws",
  base_sha: null,
  packs: [
    {
      id: REF.pack,
      path: REF.pack,
      name: null,
      templates: [
        {
          id: REF.template,
          path: `${REF.pack}/templates/${REF.template}`,
          name: null,
          default_version: REF.version,
          versions: [
            {
              version: REF.version,
              path: "x",
              status: null,
              released,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
});

const reply = (behavior: ModesBehavior) => ({
  data: referenceImpact(behavior),
  etag: null,
});
const last = (list: ImpactReport[]): ImpactReport | undefined =>
  list[list.length - 1];

const mount = (opts: { released?: boolean } = {}) => {
  vi.spyOn(packStudioApi, "tree").mockResolvedValue(
    tree(opts.released ?? false),
  );
  const reports: ImpactReport[] = [];
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ImpactBlock
          workspaceId="ws"
          versions={[REF]}
          onReport={(r) => reports.push(r)}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { reports, client };
};

const baseError = (reason: string) =>
  new ApiError("no base", "diff_base_unavailable", 409, { reason });

describe("блок «Что изменится в результате» (F10)", () => {
  beforeAll(async () => {
    await loadPackOutcomeNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("есть изменения: сводка N из M, счётчики, статусы словами, отметка нужна", async () => {
    const impact = vi
      .spyOn(packOutcomeApi, "impact")
      .mockResolvedValue(reply("normal"));
    const { reports } = mount();
    expect(await screen.findByTestId("impact-headline")).toHaveTextContent(
      "Изменится результат в 1 из 3 сценариев",
    );
    expect(impact.mock.calls[0]?.[2]).toEqual({
      base: "base",
      include_atlas: true,
    });
    expect(screen.getByTestId("impact-atlas")).toHaveTextContent(
      "изменится 4 из 12 строк, исходов было 12, станет 8",
    );
    expect(screen.getByTestId("impact-sections")).toHaveTextContent("+ 2");
    expect(screen.getByTestId("impact-scenarios")).toHaveTextContent(
      "Без изменений",
    );
    expect(screen.getByTestId("impact-scenarios")).toHaveTextContent(
      "Изменился",
    );
    expect(screen.getByTestId("impact-warning")).toBeInTheDocument();
    await waitFor(() => {
      expect(last(reports)).toMatchObject({ pending: false, needsAck: true });
    });
    expect(last(reports)?.summary).toContain("Изменится результат в 1 из 3");
  });

  it("сценарий раскрывается: изменения со знаками и «Почему?»", async () => {
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(reply("normal"));
    mount();
    const toggle = await screen.findByTestId(
      "impact-scenario-toggle-university-supervisor",
    );
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(
      await screen.findAllByTestId("outcome-change-route_step"),
    ).toHaveLength(1);
    await userEvent.click(
      screen.getAllByTestId("outcome-change-why")[0] as HTMLElement,
    );
    expect(
      (await screen.findAllByTestId("outcome-change-reasons")).length,
    ).toBeGreaterThan(0);
  });

  it("без изменений: отметка не нужна, сводки для PR нет", async () => {
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(reply("impact_same"));
    const { reports } = mount();
    expect(await screen.findByTestId("impact-headline")).toHaveTextContent(
      "Результат не изменится ни в одном из 3 сценариев",
    );
    expect(screen.queryByTestId("impact-warning")).toBeNull();
    await waitFor(() => {
      expect(last(reports)).toEqual({
        pending: false,
        needsAck: false,
        summary: "",
      });
    });
  });

  it("сценарий с ошибкой: раскрыт, показывает сообщение, отметка нужна", async () => {
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(reply("impact_error"));
    const { reports } = mount();
    expect(
      await screen.findByTestId("impact-scenario-message"),
    ).toHaveTextContent("на базе сценарий не читается");
    await waitFor(() => {
      expect(last(reports)?.needsAck).toBe(true);
    });
  });

  it("atlas: null: «слишком большой, сравнение по сценариям»", async () => {
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(
      reply("impact_atlas_null"),
    );
    mount();
    expect(await screen.findByTestId("impact-atlas")).toHaveTextContent(
      "Атлас слишком большой, сравнение по сценариям.",
    );
  });

  it("нет сценариев: подсказка, ссылка на создание, отметка не нужна", async () => {
    vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(reply("impact_empty"));
    const { reports } = mount();
    expect(
      await screen.findByTestId("impact-no-scenarios"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("impact-create-scenario")).toHaveAttribute(
      "href",
      expect.stringContaining("/result/hse-cs-sse/coursework/2026.1.6"),
    );
    await waitFor(() => {
      expect(last(reports)?.needsAck).toBe(false);
    });
  });

  it.each(["no_git", "no_base", "new_version"])(
    "базы нет, причина %s: понятный текст, расчёт не блокирует",
    async (reason) => {
      vi.spyOn(packOutcomeApi, "impact").mockRejectedValue(baseError(reason));
      const { reports } = mount();
      expect(
        await screen.findByTestId(`impact-no-base-${reason}`),
      ).toBeInTheDocument();
      await waitFor(() => {
        expect(last(reports)).toMatchObject({
          pending: false,
          needsAck: false,
        });
      });
    },
  );

  it("версия выпущена: расчёта нет, объяснение", async () => {
    const impact = vi.spyOn(packOutcomeApi, "impact");
    mount({ released: true });
    expect(await screen.findByTestId("impact-released")).toHaveTextContent(
      "выпущена и неизменяема",
    );
    expect(impact).not.toHaveBeenCalled();
  });

  it("outcome_too_large: понятный текст, повтор доступен", async () => {
    vi.spyOn(packOutcomeApi, "impact").mockRejectedValue(
      new ApiError("big", "outcome_too_large", 413, { limit: 1, size: 2 }),
    );
    mount();
    expect(await screen.findByTestId("impact-too-large")).toHaveTextContent(
      "Сравнение слишком большое",
    );
    expect(screen.getByTestId("impact-retry")).toBeEnabled();
  });

  it("сбой сервера: повтор перечитывает", async () => {
    const impact = vi
      .spyOn(packOutcomeApi, "impact")
      .mockRejectedValueOnce(new ApiError("boom", "internal_error", 400))
      .mockResolvedValue(reply("impact_same"));
    mount();
    await userEvent.click(await screen.findByTestId("impact-retry"));
    expect(await screen.findByTestId("impact-headline")).toBeInTheDocument();
    expect(impact).toHaveBeenCalledTimes(2);
  });

  it("outcome_busy повторяется сам и затем показывает результат", async () => {
    const busy = new ApiError("busy", "outcome_busy", 503, {
      retry_after_s: 0,
    });
    const impact = vi
      .spyOn(packOutcomeApi, "impact")
      .mockRejectedValueOnce(busy)
      .mockResolvedValue(reply("impact_same"));
    mount();
    expect(
      await screen.findByTestId("impact-headline", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(impact).toHaveBeenCalledTimes(2);
  });

  it("ожидание: скелет, прогресс, отмена; после отмены отчёт «не считаю», «Рассчитать» запускает заново", async () => {
    let resolve: (v: ReturnType<typeof reply>) => void = () => undefined;
    const impact = vi.spyOn(packOutcomeApi, "impact").mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const { reports } = mount();
    expect(await screen.findByTestId("impact-loading")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(last(reports)?.pending).toBe(true);
    await userEvent.click(screen.getByTestId("impact-cancel"));
    expect(await screen.findByTestId("impact-cancelled")).toBeInTheDocument();
    await waitFor(() => {
      expect(last(reports)?.pending).toBe(false);
    });
    await userEvent.click(screen.getByTestId("impact-retry"));
    await waitFor(() => {
      expect(impact).toHaveBeenCalledTimes(2);
    });
    resolve(reply("impact_same"));
    expect(await screen.findByTestId("impact-headline")).toBeInTheDocument();
  });

  it("на английском: заголовок и статусы", async () => {
    await i18n.changeLanguage("en");
    try {
      vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(reply("normal"));
      mount();
      expect(await screen.findByTestId("impact-headline")).toHaveTextContent(
        "The result will change in 1 of 3 scenarios",
      );
      expect(screen.getByTestId("impact-scenarios")).toHaveTextContent(
        "Unchanged",
      );
    } finally {
      await i18n.changeLanguage("ru");
    }
  });

  it("телефон: тот же блок, переключатель сценария доступен с клавиатуры", async () => {
    const viewport = installViewport(360);
    try {
      vi.spyOn(packOutcomeApi, "impact").mockResolvedValue(reply("normal"));
      mount();
      const toggle = await screen.findByTestId(
        "impact-scenario-toggle-university-supervisor",
      );
      toggle.focus();
      await userEvent.keyboard("{Enter}");
      expect(toggle).toHaveAttribute("aria-expanded", "true");
    } finally {
      viewport.restore();
    }
  });
});
