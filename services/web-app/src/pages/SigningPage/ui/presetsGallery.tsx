import { useState } from "react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import type { RoutePreset } from "@entities/signing-route";
import { DocPlacementPanel, PdfStampEditor } from "@features/signature-stamper";
import {
  RestorePresetDialog,
  RoutePresetBar,
  SigningRouteEditor,
} from "@features/signing-route-editor";
import type {
  PlacementResponse,
  SignaturesStateResponse,
} from "@shared/api/types";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { THREE_MARKS } from "./datesGallery";
import { galleryPdfUrl } from "./galleryPdf";

// Маршрут из шаблона (docs/design/signing-route.md, 15.7): шапка редактора маршрута («Маршрут из
// шаблона», «Изменён вами» и «Вернуть как в шаблоне»), окно подтверждения и пометки мест на
// вкладке «Подписи» («Место из шаблона», «Место изменено», «Вернуть место из шаблона»). Правки
// живут в памяти записи. Живой редактор маршрута на демо-сервере в сценарии
// `student_signing_presets`.

type Project = z.infer<typeof ProjectResponseSchema>;

const DOC = "topic_application";
const PROJECT = "gallery";

const PRESET: RoutePreset = {
  version: "2026.1.4",
  base_version: "2026.1.4",
  steps: [["author"], ["supervisor"]],
  extra_slots: [],
  optional: [],
  skipped_by_condition: [
    {
      doc_id: DOC,
      slot_id: "academic_supervisor",
      when: { person: "supervisor", role: "company" },
    },
  ],
  differs: [],
};

/** Шапка: «Вернуть» делает маршрут как в шаблоне через полсекунды, как будто ответил сервер. */
const PresetBar = ({ differs }: { differs: RoutePreset["differs"] }) => {
  const [current, setCurrent] = useState(differs);
  const [pending, setPending] = useState(false);
  return (
    <RoutePresetBar
      preset={{ ...PRESET, differs: current }}
      busy={pending}
      pending={pending}
      onRestore={() => {
        setPending(true);
        return new Promise<void>((resolve) => {
          setTimeout(() => {
            setPending(false);
            setCurrent([]);
            resolve();
          }, 500);
        });
      }}
    />
  );
};

const SLOT_DEFS = [
  {
    id: "supervisor",
    label: { ru: "Научный руководитель", en: "Supervisor" },
    applies_to: [DOC],
    default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 },
  },
  {
    id: "academic_supervisor",
    label: { ru: "Академический руководитель", en: "Academic supervisor" },
    applies_to: [DOC],
    default_placement: { page: 1, x_mm: 110, y_mm: 160, width_mm: 40 },
  },
];

const PEOPLE: Record<string, string> = {
  supervisor: "Петров П. П.",
  academic_supervisor: "Сидоров С. С.",
};

const slotInfo = {
  png_path: ".hse-studio/signatures/supervisor.png",
  natural_width_px: 600,
  natural_height_px: 240,
  signing_identity_id: null,
  sign_mode: "image" as const,
  sign_reason: "",
  signer: null,
};

const fromPack = (slotId: string): PlacementResponse => {
  const def = SLOT_DEFS.find((s) => s.id === slotId)?.default_placement;
  return {
    enabled: true,
    page: def?.page ?? 1,
    x_mm: def?.x_mm ?? 110,
    y_mm: def?.y_mm ?? 130,
    width_mm: def?.width_mm ?? 40,
    sign_date: null,
    dates:
      slotId === "supervisor"
        ? THREE_MARKS.map((mark, i) => ({
            ...mark,
            id: `d${String(i + 1)}`,
            text: null,
          }))
        : [],
    signed_at: null,
    origin: "pack",
    preset_available: true,
  };
};

/** Вкладка «Подписи» документа: место научрука из шаблона, место академрука сдвинуто руками. */
const PlacesEditor = () => {
  const [placements, setPlacements] = useState<
    Record<string, PlacementResponse>
  >({
    supervisor: fromPack("supervisor"),
    academic_supervisor: {
      ...fromPack("academic_supervisor"),
      x_mm: 130,
      y_mm: 184,
      origin: "manual",
    },
  });
  const [restoring, setRestoring] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const state: SignaturesStateResponse = {
    slots: { supervisor: slotInfo, academic_supervisor: slotInfo },
    placements: { [DOC]: placements },
  };
  const move = (slotId: string, patch: Partial<PlacementResponse>) => {
    setPlacements((prev) => {
      const current = prev[slotId];
      return current
        ? { ...prev, [slotId]: { ...current, ...patch, origin: "manual" } }
        : prev;
    });
  };
  return (
    <div
      className="doc-signatures-grid"
      style={{
        display: "grid",
        gridTemplateColumns: "18.75rem minmax(0, 1fr)",
        height: 680,
        border: "1px solid var(--border)",
        borderRadius: "var(--r-2)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          borderRight: "1px solid var(--border)",
          background: "var(--bg-1)",
          overflowY: "auto",
          minHeight: 0,
        }}
      >
        <DocPlacementPanel
          projectId={PROJECT}
          docId={DOC}
          pdfAvailable
          slotDefs={SLOT_DEFS}
          state={state}
          lang="ru"
          currentPage={page}
          pageCount={pageCount}
          personNameForSlot={(slotId) => PEOPLE[slotId] ?? null}
          onPlacementChange={move}
          onJumpToPage={setPage}
          onOpenProjectSignatures={() => undefined}
          onSlotModeChange={() => undefined}
          placeControl={{
            canRestore: true,
            isRestoring: (slotId) => restoring === slotId,
            onRestore: (slotId) => {
              setRestoring(slotId);
              setTimeout(() => {
                setRestoring(null);
                setPlacements((prev) => ({
                  ...prev,
                  [slotId]: fromPack(slotId),
                }));
              }, 500);
            },
          }}
        />
      </div>
      <div className="flex flex-col" style={{ minHeight: 0, minWidth: 0 }}>
        <PdfStampEditor
          projectId={PROJECT}
          docId={DOC}
          pdfRelPath="output/topic_application.pdf"
          pdfUrl={galleryPdfUrl()}
          pdfAvailable
          slotDefs={SLOT_DEFS}
          state={state}
          page={page}
          onPageChange={setPage}
          onPageCountChange={setPageCount}
          onPlacementChange={move}
          docLang="ru"
        />
      </div>
    </div>
  );
};

/** Проект демо-сервера для живого редактора: только то, что экран читает. */
const demoProject = (id: string): Project =>
  ({ id, authors: [], lang: "ru" }) as unknown as Project;

const editorEntry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  note: string,
): GalleryEntry => ({ id, title, frame: "window", width: 1120, render, note });

/** Записи группы `signing-route-presets`. */
export const routePresetEntries = (): GalleryEntry[] => [
  editorEntry(
    "route_preset_template",
    "Шапка: маршрут из шаблона",
    () => <PresetBar differs={[]} />,
    "Порядок, подписи сверх точки и отметки «необязательна» как в шаблоне: пометка без кнопки, версия шаблона в подсказке.",
  ),
  editorEntry(
    "route_preset_changed",
    "Шапка: изменён вами",
    () => <PresetBar differs={["order", "slots"]} />,
    "Что отличается, и «Вернуть как в шаблоне»: окно подтверждения, затем снова «Маршрут из шаблона».",
  ),
  {
    id: "route_preset_confirm",
    title: "Подтверждение «Вернуть как в шаблоне?»",
    note: "Люди остаются, если их роль есть в шаблоне; места подписей на страницах не меняются.",
    frame: "plain",
    render: () => (
      <DialogLauncher label="Открыть окно" defaultOpen={false}>
        {({ isOpen, close }) => (
          <RestorePresetDialog
            isOpen={isOpen}
            pending={false}
            onConfirm={close}
            onCancel={close}
          />
        )}
      </DialogLauncher>
    ),
  },
  editorEntry(
    "signature_place_origin",
    "Вкладка «Подписи»: место из шаблона и изменённое",
    () => <PlacesEditor />,
    "У научрука «Место из шаблона» с метками даты пака; место академрука сдвинуто: «Место изменено» и «Вернуть место из шаблона». Сдвиньте рамку научрука, и она станет изменённой.",
  ),
  {
    id: "route_preset_live_fresh",
    title: "Живой редактор: черновик по шаблону",
    note: "«Bertie»: черновик создаётся при открытии, места из шаблона включены, у научрука метки даты, академрук с подсказкой условия.",
    frame: "screen",
    scenario: "student_signing_presets",
    render: () => (
      <SigningRouteEditor
        project={demoProject("p_01hxa1c4de")}
        profileId="topic-approval"
      />
    ),
  },
  {
    id: "route_preset_live_changed",
    title: "Живой редактор: изменённый черновик",
    note: "«Практика 2025»: академрук добавлен вами, место научрука сдвинуто. Есть «Вернуть как в шаблоне» и «Вернуть место из шаблона».",
    frame: "screen",
    scenario: "student_signing_presets",
    render: () => (
      <SigningRouteEditor
        project={demoProject("p_01hxa4n7pq")}
        profileId="topic-approval"
      />
    ),
  },
];
