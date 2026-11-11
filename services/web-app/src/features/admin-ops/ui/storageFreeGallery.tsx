import { useEffect, useState, type ReactNode } from "react";
import type {
  AdminStorage,
  AdminStorageOwnerRow,
  LifecycleSweep,
  LifecycleSweepPreview,
} from "@entities/session";
import {
  NO_REPORTS_DISK_SUMMARY,
  makeRunnerDiskSummary,
} from "@entities/runner/testing";
import type { RunnerDiskSummary } from "@entities/runner";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { Modal } from "@shared/ui";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { useOwnerListState } from "../lib/lists";
import { ensureAdminOpsLocales } from "../lib/locales";
import type { ViewStatus } from "../lib/viewStatus";
import {
  SWEEP_NOW,
  SWEEP_PREVIEWS,
  SWEEP_STATES,
  type SweepStateId,
} from "../testing/sweepFixtures";
import { Storage } from "./Storage";
import {
  FreeSpacePanel,
  type FreeSpacePanelProps,
  type FreeSpacePreviewState,
} from "./StorageFreeSpace";
import { StorageMoreSpace } from "./StorageMoreSpace";
import { StorageView } from "./StorageView";

// Галерея «Хранилище: освободить место» (docs/design/storage-cleanup.md, 4.5): окно
// «Освободить место» в каждом состоянии на эталонах SWEEP_PREVIEWS и SWEEP_STATES, плашка
// прогона на странице, блок «Где ещё» со сводкой раннеров и без отчётов, телефон и живые
// записи на демо-мире. Время постоянное (SWEEP_NOW), чтобы галерея не плыла.

const NOW = Date.parse(SWEEP_NOW);
const DIALOG_W = 640;
const PAGE_W = 900;
const PHONE = 390;
const GIB = 1024 ** 3;
const noop = () => undefined;

/** Словари админки грузятся вместе с её чанком; галерея ждёт их сама. */
const Ready = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminOpsLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  return ready ? <>{children}</> : null;
};

const entry = (
  id: string,
  title: string,
  render: () => ReactNode,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: DIALOG_W,
  render: () => <Ready>{render()}</Ready>,
  ...extra,
});

const ready = (preview: LifecycleSweepPreview): FreeSpacePreviewState => ({
  status: "ready",
  preview,
});

const panel = (props: Partial<FreeSpacePanelProps> = {}) => (
  <FreeSpacePanel
    mode="preview"
    preview={ready(SWEEP_PREVIEWS.default)}
    sweep={null}
    now={NOW}
    onConfirm={noop}
    onStop={noop}
    onClose={noop}
    {...props}
  />
);

const sweepPanel = (state: SweepStateId) =>
  panel({ mode: "sweep", sweep: SWEEP_STATES[state] });

// ── страница «Хранилища» вокруг плашки и блока «Где ещё» ──

const STORAGE: AdminStorage = {
  blob_count: 1840,
  blob_bytes: Math.round(2.1 * GIB),
  projects: 38,
  deleted_projects: 3,
  free_bytes: Math.round(9.4 * GIB),
  volume_total_bytes: 200 * GIB,
  computed_at: new Date(NOW - 40_000).toISOString(),
  owners: [],
};

const OWNERS: AdminStorageOwnerRow[] = [
  ["u3", "Мария Келлер", "maria.keller", 12],
  ["u4", "Иван Сидоров", "ivan.sidorov", 9],
  ["u2", "Пётр Орлов", "petr.orlov", 6],
].map(([id, name, mail, projects]) => ({
  kind: "user" as const,
  id: String(id),
  name: String(name),
  email: `${String(mail)}@example.org`,
  projects: Number(projects),
  bytes: Number(projects) * 48 * 1024 ** 2,
}));

const PageDemo = ({
  sweep = null,
  summary = makeRunnerDiskSummary(),
  summaryStatus = "ready",
}: {
  sweep?: LifecycleSweep | null;
  summary?: RunnerDiskSummary | null;
  summaryStatus?: ViewStatus;
}) => {
  const state = useOwnerListState();
  return (
    <StorageView
      status="ready"
      storage={STORAGE}
      owners={{
        status: "ready",
        items: OWNERS,
        total: OWNERS.length,
        fetching: false,
        failed: false,
        state,
        pagination: {
          page: state.page,
          pageSize: state.pageSize,
          total: OWNERS.length,
          onPageChange: state.setPage,
          pageSizes: state.pageSizes,
          onPageSizeChange: state.setPageSize,
        },
        onRetry: noop,
      }}
      now={NOW}
      freeSpace={{
        sweep,
        onFreeSpace: noop,
        onDetails: noop,
        onHide: noop,
      }}
      moreSpace={{
        status: summaryStatus,
        summary,
        onRetry: noop,
        onOpenRunner: noop,
      }}
    />
  );
};

const more = (summary: RunnerDiskSummary | null, status: ViewStatus) => (
  <StorageMoreSpace
    status={status}
    summary={summary}
    now={NOW}
    onRetry={noop}
    onOpenRunner={noop}
  />
);

/** Окно целиком по кнопке: на телефоне это шторка снизу. */
const DialogPreview = () => (
  <DialogLauncher label="Открыть окно «Освободить место»">
    {({ isOpen, close }) => (
      <Modal
        isOpen={isOpen}
        onClose={close}
        width={DIALOG_W}
        title="Освободить место сейчас?"
      >
        {panel({ onClose: close })}
      </Modal>
    )}
  </DialogLauncher>
);

const live = (scenario: string) => ({ scenario, width: PAGE_W });

export const getStorageFreeGallery = (): GalleryGroup[] => [
  {
    id: "admin-ops-storage-free",
    title: "Хранилище: освободить место",
    description:
      "«Освободить место» прогоняет на сервере все ручные очистки «Хранения данных»: предпросмотр по источникам, ход, итог записями и местом на диске. Ниже блок «Где ещё освободить место» со сводкой дисков общих раннеров.",
    entries: [
      entry("free_preview", "Предпросмотр", () => panel(), {
        note: "Срок, число записей и размер по каждому источнику, исключённые с причиной.",
      }),
      entry(
        "free_preview_nothing",
        "Предпросмотр: нечего",
        () => panel({ preview: ready(SWEEP_PREVIEWS.nothing) }),
        { note: "Кнопка подтверждения выключена." },
      ),
      entry(
        "free_preview_capped",
        "Предпросмотр с потолком",
        () => panel({ preview: ready(SWEEP_PREVIEWS.capped) }),
        {
          note: "Счёт до 100 000; один источник не посчитался за 3 с.",
        },
      ),
      entry("free_preview_loading", "Предпросмотр считается", () =>
        panel({ preview: { status: "loading" } }),
      ),
      entry("free_preview_error", "Предпросмотр не посчитался", () =>
        panel({ preview: { status: "error", onRetry: noop } }),
      ),
      entry("free_preview_busy", "Отказ: прогон уже идёт", () =>
        panel({ error: "Очистка уже идёт. Дождитесь её итога." }),
      ),
      entry("free_running", "Прогон идёт", () => sweepPanel("running"), {
        note: "Текущий источник, номер из семи, «Остановить после текущего источника».",
      }),
      entry("free_cancelling", "Останавливается", () =>
        sweepPanel("cancelling"),
      ),
      entry("free_done", "Итог", () => sweepPanel("done"), {
        note: "Отдельно удалено записей и освобождено на диске, пояснение про базу.",
      }),
      entry("free_done_more", "Итог: остаток позже", () =>
        sweepPanel("done_more"),
      ),
      entry("free_error", "Итог с ошибкой источника", () =>
        sweepPanel("error"),
      ),
      entry("free_cancelled", "Остановлено", () => sweepPanel("cancelled")),
      entry("free_interrupted", "Прервано перезапуском", () =>
        sweepPanel("interrupted"),
      ),
      entry(
        "free_page_running",
        "Страница: прогон идёт",
        () => <PageDemo sweep={SWEEP_STATES.running} />,
        {
          width: PAGE_W,
          note: "Окно закрыли, ход виден в плашке под шапкой.",
        },
      ),
      entry(
        "free_page_done",
        "Страница: итог прошлого прогона",
        () => <PageDemo sweep={SWEEP_STATES.done} />,
        { width: PAGE_W, note: "Итог виден сутки, скрывается кнопкой." },
      ),
      entry(
        "free_page_interrupted",
        "Страница: прогон прервался",
        () => <PageDemo sweep={SWEEP_STATES.interrupted} />,
        { width: PAGE_W },
      ),
      entry(
        "free_more_runners",
        "«Где ещё»: раннеры с замером",
        () => more(makeRunnerDiskSummary(), "ready"),
        { note: "До трёх раннеров по объёму, каждый открывает окно «Диск»." },
      ),
      entry("free_more_none", "«Где ещё»: раннеры без отчётов", () =>
        more(NO_REPORTS_DISK_SUMMARY, "ready"),
      ),
      entry(
        "free_more_clean",
        "«Где ещё»: на раннерах нечего освобождать",
        () =>
          more(
            makeRunnerDiskSummary({
              outdated: 0,
              cleanable_bytes: 0,
              top: [],
            }),
            "ready",
          ),
      ),
      entry("free_more_loading", "«Где ещё»: сводка грузится", () =>
        more(null, "loading"),
      ),
      entry("free_more_error", "«Где ещё»: сводка не загрузилась", () =>
        more(null, "error"),
      ),
      entry("free_phone_preview", "Телефон: предпросмотр", () => panel(), {
        width: PHONE,
      }),
      entry(
        "free_phone_running",
        "Телефон: прогон идёт",
        () => sweepPanel("running"),
        { width: PHONE },
      ),
      entry(
        "free_phone_page",
        "Телефон: страница с итогом",
        () => <PageDemo sweep={SWEEP_STATES.done} />,
        { width: PHONE },
      ),
      {
        id: "free_dialog",
        title: "Окно «Освободить место» целиком",
        note: "На телефоне окно становится шторкой снизу.",
        frame: "plain",
        render: () => (
          <Ready>
            <DialogPreview />
          </Ready>
        ),
      },
      entry(
        "free_live",
        "Живое: освободить место",
        () => <Storage />,
        live("admin_ready"),
      ),
      entry(
        "free_live_nothing",
        "Живое: удалять нечего, раннеров нет",
        () => <Storage />,
        live("ops_fresh"),
      ),
      entry(
        "free_live_capped",
        "Живое: счёт с потолком",
        () => <Storage />,
        live("ops_services_degraded"),
      ),
    ],
  },
];
