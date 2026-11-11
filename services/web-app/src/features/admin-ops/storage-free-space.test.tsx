import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { RunnerDiskSummarySchema } from "@entities/runner";
import {
  NO_REPORTS_DISK_SUMMARY,
  makeRunnerDiskSummary,
} from "@entities/runner/testing";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { ensureAdminOpsLocales } from "./lib/locales";
import {
  excludedByReason,
  isSweepRecent,
  sweepProgress,
  SWEEP_RECENT_MS,
} from "./lib/sweep";
import { SWEEP_NOW, SWEEP_PREVIEWS, SWEEP_STATES } from "./testing";
import {
  FreeSpacePanel,
  SweepBanner,
  SweepStatus,
  type FreeSpacePanelProps,
} from "./ui/StorageFreeSpace";
import { StorageMoreSpace } from "./ui/StorageMoreSpace";
import { getStorageFreeGallery } from "./ui/storageFreeGallery";
import { StoragePage } from "./index";

// «Освободить место» и «Где ещё освободить место» в «Хранилище» (docs/design/storage-cleanup.md,
// 4.3): предпросмотр, «нечего», ход, итог, прерывание, плашка, сводка раннеров; затем страница
// целиком на демо-мире.

const NOW = Date.parse(SWEEP_NOW);
const noop = () => undefined;

const wrap = (node: ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const panel = (props: Partial<FreeSpacePanelProps> = {}) =>
  wrap(
    <FreeSpacePanel
      mode="preview"
      preview={{ status: "ready", preview: SWEEP_PREVIEWS.default }}
      sweep={null}
      now={NOW}
      onConfirm={noop}
      onStop={noop}
      onClose={noop}
      {...props}
    />,
  );

beforeAll(async () => {
  installServerDemo();
  await ensureAdminOpsLocales();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  activateServerScenario("admin_ready");
});
afterEach(cleanup);

describe("«Освободить место»: правила показа", () => {
  it("номер текущего источника и число пройденных у закрытого", () => {
    expect(sweepProgress(SWEEP_STATES.running)).toMatchObject({
      n: 3,
      total: 7,
    });
    expect(sweepProgress(SWEEP_STATES.running).current?.key).toBe(
      "notifications",
    );
    expect(sweepProgress(SWEEP_STATES.done)).toMatchObject({
      n: 7,
      current: null,
    });
    expect(sweepProgress(SWEEP_STATES.interrupted).n).toBe(5);
  });

  it("исключённые группируются по причине", () => {
    const groups = excludedByReason(SWEEP_PREVIEWS.default);
    expect(groups.map(([reason]) => reason)).toEqual([
      "protected",
      "own_task",
      "on_write",
      "infra",
    ]);
    expect(groups[0]?.[1]).toEqual(["audit_log"]);
  });

  it("итог виден сутки, идущий прогон всегда", () => {
    const end = Date.parse(SWEEP_STATES.done.finished_at ?? "");
    expect(isSweepRecent(SWEEP_STATES.done, end + SWEEP_RECENT_MS)).toBe(true);
    expect(isSweepRecent(SWEEP_STATES.done, end + SWEEP_RECENT_MS + 1)).toBe(
      false,
    );
    expect(isSweepRecent(SWEEP_STATES.running, NOW + 7 * SWEEP_RECENT_MS)).toBe(
      true,
    );
  });
});

describe("«Освободить место»: окно", () => {
  it("предпросмотр: срок, число записей, размер, исключённые с причиной", () => {
    render(panel());
    const ai = screen.getByTestId("sweep-source-ai_usage");
    expect(ai).toHaveTextContent("Журнал вызовов ИИ");
    expect(ai).toHaveTextContent("старше 90 дн.");
    expect(ai).toHaveTextContent(/около 77\s564 записей/);
    expect(ai).toHaveTextContent("412 МБ");
    expect(screen.getByTestId("sweep-source-notifications")).toHaveTextContent(
      "нечего",
    );
    expect(screen.getByTestId("sweep-source-guest_sessions")).toHaveTextContent(
      "7 суток после истечения",
    );
    expect(screen.getByTestId("sweep-source-collab_state")).toHaveTextContent(
      "около 12 файлов",
    );
    const excluded = screen.getByTestId("sweep-excluded");
    expect(excluded).toHaveTextContent("«Журнал аудита»: вручную не чистится");
    expect(excluded).toHaveTextContent("«Удалённые проекты»");
    expect(excluded).toHaveTextContent("своя фоновая задача по расписанию");
    expect(screen.getByTestId("sweep-confirm")).toBeEnabled();
    expect(screen.queryByTestId("sweep-nothing")).toBeNull();
  });

  it("потолок счёта и источник, который не удалось посчитать", () => {
    render(
      panel({ preview: { status: "ready", preview: SWEEP_PREVIEWS.capped } }),
    );
    expect(screen.getByTestId("sweep-source-ai_usage")).toHaveTextContent(
      /больше 100\s000 записей/,
    );
    expect(screen.getByTestId("sweep-source-share_links")).toHaveTextContent(
      "не удалось посчитать",
    );
    expect(screen.getByTestId("sweep-capped")).toHaveTextContent(
      /Счёт идёт до 100\s000/,
    );
  });

  it("нечего удалять: кнопка выключена и сказано почему", () => {
    render(
      panel({ preview: { status: "ready", preview: SWEEP_PREVIEWS.nothing } }),
    );
    expect(screen.getByTestId("sweep-nothing")).toHaveTextContent(
      "Сейчас удалять нечего",
    );
    expect(screen.getByTestId("sweep-confirm")).toBeDisabled();
  });

  it("предпросмотр не посчитался: ошибка с повтором, подтверждать нечего", () => {
    render(panel({ preview: { status: "error", onRetry: noop } }));
    expect(screen.getByTestId("sweep-preview-error")).toHaveTextContent(
      "Не удалось посчитать",
    );
    expect(screen.getByTestId("sweep-confirm")).toBeDisabled();
  });

  it("ход: текущий источник, номер, остановка", async () => {
    const stopped: string[] = [];
    render(
      panel({
        mode: "sweep",
        sweep: SWEEP_STATES.running,
        onStop: (id) => stopped.push(id),
      }),
    );
    expect(screen.getByTestId("sweep-title")).toHaveTextContent(
      "Чистим: Входящие (3 из 7)",
    );
    expect(screen.getByTestId("sweep-step-ai_usage")).toHaveAttribute(
      "data-status",
      "done",
    );
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("sweep-stop"));
    expect(stopped).toEqual([SWEEP_STATES.running.id]);
  });

  it("остановка после текущего: кнопки нет, сказано, что останавливаем", () => {
    render(panel({ mode: "sweep", sweep: SWEEP_STATES.cancelling }));
    expect(screen.getByTestId("sweep-title")).toHaveTextContent(
      "Останавливаем после текущего источника: Приглашения",
    );
    expect(screen.queryByTestId("sweep-stop")).toBeNull();
  });

  it("итог: отдельно записи и место на диске, пояснение S11", () => {
    render(panel({ mode: "sweep", sweep: SWEEP_STATES.done }));
    expect(screen.getByTestId("sweep-title")).toHaveTextContent(
      /Готово: удалено 78\s823 записи, освобождено на диске 188 МБ\./,
    );
    expect(screen.getByTestId("sweep-note")).toHaveTextContent(
      "освобождают место внутри базы",
    );
    expect(screen.getByTestId("sweep-step-ai_usage")).toHaveTextContent(
      /удалено 77\s564, 176 МБ на диске/,
    );
    expect(screen.getByTestId("sweep-step-notifications")).toHaveTextContent(
      "нечего",
    );
    expect(screen.queryByTestId("sweep-more")).toBeNull();
    expect(screen.queryByTestId("sweep-stop")).toBeNull();
  });

  it("бюджет кончился: остаток при плановой очистке", () => {
    render(panel({ mode: "sweep", sweep: SWEEP_STATES.done_more }));
    expect(screen.getByTestId("sweep-more")).toHaveTextContent(
      "при следующей плановой очистке",
    );
    expect(screen.getByTestId("sweep-step-ai_usage")).toHaveTextContent(
      "остальное позже",
    );
  });

  it("ошибка источника: прогон с ошибками, причина у шага", () => {
    render(panel({ mode: "sweep", sweep: SWEEP_STATES.error }));
    expect(screen.getByTestId("sweep-title")).toHaveTextContent(
      "Очистка завершилась с ошибками",
    );
    expect(screen.getByTestId("sweep-step-jobs")).toHaveTextContent(
      "statement timeout",
    );
  });

  it("прерван: шаг прерван перезапуском, остальные не дошли", () => {
    render(wrap(<SweepStatus sweep={SWEEP_STATES.interrupted} now={NOW} />));
    expect(screen.getByTestId("sweep-title")).toHaveTextContent(
      "Прогон прервался: сервер перезапустился",
    );
    expect(screen.getByTestId("sweep-step-share_links")).toHaveTextContent(
      "прервано перезапуском сервера",
    );
    expect(screen.getByTestId("sweep-step-collab_state")).toHaveTextContent(
      "не дошли",
    );
    expect(screen.queryByTestId("sweep-note")).toBeNull();
  });

  it("плашка прошлого прогона: итог, подробнее, скрыть", async () => {
    const calls: string[] = [];
    render(
      wrap(
        <SweepBanner
          sweep={SWEEP_STATES.interrupted}
          now={NOW}
          onDetails={() => calls.push("details")}
          onHide={() => calls.push("hide")}
        />,
      ),
    );
    const banner = screen.getByTestId("sweep-banner");
    expect(banner).toHaveTextContent("Прогон прервался");
    await userEvent.click(screen.getByTestId("sweep-banner-details"));
    await userEvent.click(screen.getByTestId("sweep-banner-hide"));
    expect(calls).toEqual(["details", "hide"]);
  });

  it("идущий прогон в плашке не скрывается", () => {
    render(
      wrap(
        <SweepBanner
          sweep={SWEEP_STATES.running}
          now={NOW}
          onDetails={noop}
          onHide={noop}
        />,
      ),
    );
    expect(screen.queryByTestId("sweep-banner-hide")).toBeNull();
  });

  it("английский", async () => {
    await i18n.changeLanguage("en");
    render(panel({ mode: "sweep", sweep: SWEEP_STATES.done }));
    expect(screen.getByTestId("sweep-title")).toHaveTextContent(
      /Done: 78,823 records deleted, 188 MB freed on disk\./,
    );
  });
});

describe("«Где ещё освободить место»", () => {
  it("состояния галереи совпадают с эталонами сводки contracts/server (B6)", () => {
    const fixture = (name: string): unknown =>
      RunnerDiskSummarySchema.parse(
        JSON.parse(
          readFileSync(
            join(
              import.meta.dirname,
              "..",
              "..",
              "..",
              "..",
              "..",
              "contracts",
              "server",
              "fixtures",
              "RunnerDiskSummary",
              `${name}.json`,
            ),
            "utf8",
          ),
        ),
      );
    expect(makeRunnerDiskSummary()).toEqual(fixture("default"));
    expect(NO_REPORTS_DISK_SUMMARY).toEqual(fixture("none"));
  });

  it("сводка раннеров: сколько можно освободить и до трёх раннеров", async () => {
    const opened: string[] = [];
    render(
      wrap(
        <StorageMoreSpace
          status="ready"
          summary={makeRunnerDiskSummary()}
          now={NOW}
          onOpenRunner={(r) => opened.push(r.name)}
        />,
      ),
    );
    expect(screen.getByTestId("more-data")).toHaveAttribute(
      "href",
      "/admin/data",
    );
    expect(screen.getByTestId("more-all-runners")).toHaveAttribute(
      "href",
      "/admin/runners",
    );
    expect(screen.getByTestId("more-runners-total")).toHaveTextContent(
      "на общих раннерах можно освободить 32 ГБ",
    );
    const top = within(screen.getByTestId("more-runners-top"));
    expect(top.getAllByRole("listitem")).toHaveLength(3);
    await userEvent.click(top.getByText("runner-4"));
    expect(opened).toEqual(["runner-4"]);
    expect(screen.getByTestId("more-runners-outdated")).toHaveTextContent(
      "Ещё 1 раннер не сообщает о диске",
    );
    expect(screen.getByTestId("more-not-included")).toHaveTextContent(
      "Образы на узлах Kubernetes удаляет сам Kubernetes",
    );
  });

  it("ни один раннер не сообщает о диске: обновите до версии", () => {
    render(
      wrap(
        <StorageMoreSpace
          status="ready"
          summary={NO_REPORTS_DISK_SUMMARY}
          now={NOW}
          onOpenRunner={noop}
        />,
      ),
    );
    expect(screen.getByTestId("more-runners-none")).toHaveTextContent(
      `обновите их до ${NO_REPORTS_DISK_SUMMARY.min_version}`,
    );
    expect(screen.queryByTestId("more-runners-top")).toBeNull();
  });

  it("сводка не загрузилась: строка с повтором, ссылки на месте", () => {
    render(
      wrap(
        <StorageMoreSpace
          status="error"
          summary={null}
          now={NOW}
          onRetry={noop}
          onOpenRunner={noop}
        />,
      ),
    );
    expect(screen.getByTestId("more-runners-error")).toHaveTextContent(
      "Не удалось загрузить сводку",
    );
    expect(screen.getByTestId("more-data")).toBeInTheDocument();
  });
});

describe("«Хранилище» на демо-мире", () => {
  it("предпросмотр, запуск, ход, остановка и плашка итога", async () => {
    const user = userEvent.setup();
    render(wrap(<StoragePage />));
    await user.click(await screen.findByTestId("storage-free-space"));
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByTestId("sweep-source-ai_usage"),
    ).toHaveTextContent(/около 77\s564 записей/);
    await user.click(within(dialog).getByTestId("sweep-confirm"));
    expect(await within(dialog).findByTestId("sweep-status")).toHaveAttribute(
      "data-status",
      "running",
    );
    expect(within(dialog).getByTestId("sweep-title")).toHaveTextContent(
      "Чистим: Журнал вызовов ИИ (1 из 7)",
    );
    await user.click(within(dialog).getByTestId("sweep-stop"));
    await waitFor(
      () => {
        expect(within(dialog).getByTestId("sweep-status")).toHaveAttribute(
          "data-status",
          "cancelled",
        );
      },
      { timeout: 8000 },
    );
    expect(within(dialog).getByTestId("sweep-title")).toHaveTextContent(
      "Остановлено",
    );
    await user.click(within(dialog).getByText("Закрыть"));
    const banner = await screen.findByTestId("sweep-banner");
    expect(banner).toHaveAttribute("data-status", "cancelled");
    await user.click(within(banner).getByTestId("sweep-banner-hide"));
    expect(screen.queryByTestId("sweep-banner")).toBeNull();
  }, 20_000);

  it("чистая установка: удалять нечего, раннеры не прислали замер", async () => {
    activateServerScenario("ops_fresh");
    const user = userEvent.setup();
    render(wrap(<StoragePage />));
    expect(await screen.findByTestId("more-runners-none")).toHaveTextContent(
      "Раннеры ещё не прислали замер диска",
    );
    await user.click(screen.getByTestId("storage-free-space"));
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByTestId("sweep-nothing"),
    ).toBeInTheDocument();
    expect(within(dialog).getByTestId("sweep-confirm")).toBeDisabled();
  }, 20_000);

  it("диск раннера открывается из сводки", async () => {
    const user = userEvent.setup();
    render(wrap(<StoragePage />));
    const total = await screen.findByTestId("more-runners-total");
    expect(total).toHaveTextContent("можно освободить");
    await user.click(screen.getByTestId("more-runner-rn_01hxb1"));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Диск раннера «runner-1»");
  }, 20_000);
});

describe("галерея «Хранилище: освободить место»", () => {
  const entries = getStorageFreeGallery().flatMap((g) => g.entries);

  it("есть состояния раздела 4.5", () => {
    const ids = entries.map((e) => e.id);
    for (const id of [
      "free_preview",
      "free_preview_nothing",
      "free_preview_capped",
      "free_running",
      "free_done",
      "free_interrupted",
      "free_more_runners",
      "free_more_none",
    ]) {
      expect(ids).toContain(id);
    }
  });

  it.each(["ru", "en"])(
    "язык %s: записи без демо-мира рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of entries.filter((e) => e.scenario === undefined)) {
        const { container, unmount } = render(wrap(entry.render()));
        await waitFor(() => {
          expect(container.textContent).not.toBe("");
        });
        expect(container.textContent).not.toMatch(
          /(?<!\s)\b(storage|free|confirm|more|step|banner|lifecycle)\.[a-z]+[A-Za-z.]*/,
        );
        unmount();
      }
    },
    20_000,
  );
});
