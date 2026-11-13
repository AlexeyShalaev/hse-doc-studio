import { useState, type ReactNode } from "react";
import { formatDateMark, type DateMarkInput } from "@entities/signature";
import {
  DocPlacementPanel,
  PdfStampEditor,
  ResetSignaturesDialog,
  type DateMarksSave,
  type SlotDateRoute,
} from "@features/signature-stamper";
import type {
  DateMarkResponse,
  PlacementResponse,
  SignaturesStateResponse,
  SignedAtResponse,
} from "@shared/api/types";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { galleryPdfUrl } from "./galleryPdf";

// Дата подписания в редакторе размещения (docs/design/signing-route.md, 14.11): та же панель
// «Подписи» документа и превью с рамками, что во вкладке документа, на образце PDF галереи.
// Правки живут в памяти записи: метки двигаются, формат и ручная дата меняются, текст считается
// по моменту подписи слота, как на сервере. Сервер и маршрут не нужны.

const DOC = "topic_application";
const PROJECT = "gallery";

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
  png_path: null,
  natural_width_px: 600,
  natural_height_px: 240,
  signing_identity_id: null,
  sign_mode: "image" as const,
  sign_reason: "",
  signer: null,
};

type Mark = Omit<DateMarkInput, "id">;

/** «« 13 » ноября 2026 г.» тремя метками на заготовке даты под строкой научрука. */
export const THREE_MARKS: Mark[] = [
  {
    page: 1,
    x_mm: 111.6,
    y_mm: 150,
    width_mm: 6.4,
    height_mm: 5,
    format: "day",
    align: "center",
  },
  {
    page: 1,
    x_mm: 122,
    y_mm: 150,
    width_mm: 23,
    height_mm: 5,
    format: "month_word",
    align: "center",
  },
  {
    page: 1,
    x_mm: 151.3,
    y_mm: 150,
    width_mm: 5,
    height_mm: 5,
    format: "year_short",
    align: "left",
  },
];

/** Дата академрука на второй странице. */
const SECOND_PAGE: Mark = {
  page: 2,
  x_mm: 120,
  y_mm: 250,
  width_mm: 40,
  height_mm: 5,
  format: "date_long",
  align: "left",
};

type SlotSetup = {
  marks: Mark[];
  signedAt: SignedAtResponse | null;
  /** null: слот вне маршрута; иначе способ участника. */
  route: SlotDateRoute | null;
  enabled?: boolean;
};

const APPROVED: SignedAtResponse = {
  at: "2026-11-13T07:30:00+00:00",
  source: "approval",
};

const withText = (
  marks: readonly (Mark & { id?: string | null })[],
  signedAt: SignedAtResponse | null,
  lang: string,
): DateMarkResponse[] =>
  marks.map((mark, i) => ({
    ...mark,
    id: mark.id ?? `d${String(i + 1)}`,
    text:
      signedAt === null ? null : formatDateMark(signedAt.at, mark.format, lang),
  }));

const placementOf = (
  setup: SlotSetup,
  slotId: string,
  lang: string,
): PlacementResponse => {
  const def = SLOT_DEFS.find((s) => s.id === slotId)?.default_placement;
  return {
    enabled: setup.enabled ?? true,
    page: def?.page ?? 1,
    x_mm: def?.x_mm ?? 110,
    y_mm: def?.y_mm ?? 130,
    width_mm: def?.width_mm ?? 40,
    sign_date: null,
    dates: withText(setup.marks, setup.signedAt, lang),
    signed_at: setup.signedAt,
  };
};

const DatesEditor = ({
  slots,
  initialPage = 1,
  lang = "ru",
}: {
  slots: Record<string, SlotSetup>;
  initialPage?: number;
  lang?: string;
}) => {
  const [setups, setSetups] = useState(slots);
  const [page, setPage] = useState(initialPage);
  const [pageCount, setPageCount] = useState(0);
  const placements = Object.fromEntries(
    Object.entries(setups).map(([slotId, setup]) => [
      slotId,
      placementOf(setup, slotId, lang),
    ]),
  );
  const state: SignaturesStateResponse = {
    slots: { supervisor: slotInfo, academic_supervisor: slotInfo },
    placements: { [DOC]: placements },
  };

  const save = (slotId: string, body: DateMarksSave) => {
    setSetups((prev) => {
      const current = prev[slotId];
      if (!current) return prev;
      const signedAt =
        body.signed_at === undefined
          ? current.signedAt
          : body.signed_at === null
            ? null
            : { at: body.signed_at.date, source: "manual" as const };
      return {
        ...prev,
        [slotId]: { ...current, marks: body.dates, signedAt },
      };
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
          slotDefs={SLOT_DEFS.filter((s) => s.id in setups)}
          state={state}
          lang={lang}
          currentPage={page}
          pageCount={pageCount}
          personNameForSlot={(slotId) => PEOPLE[slotId] ?? null}
          onPlacementChange={() => undefined}
          onJumpToPage={setPage}
          onOpenProjectSignatures={() => undefined}
          onSlotModeChange={() => undefined}
          dateControl={{
            canEdit: true,
            route: (slotId) => setups[slotId]?.route ?? null,
            isSaving: () => false,
            onSave: save,
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
          slotDefs={SLOT_DEFS.filter((s) => s.id in setups)}
          state={state}
          page={page}
          onPageChange={setPage}
          onPageCountChange={setPageCount}
          onPlacementChange={() => undefined}
          docLang={lang}
          onDateMarkChange={(slotId, index, place) => {
            const setup = setups[slotId];
            if (!setup) return;
            save(slotId, {
              dates: setup.marks.map((mark, i) => ({
                ...mark,
                id: null,
                ...(i === index ? place : {}),
              })),
            });
          }}
        />
      </div>
    </div>
  );
};

const editorEntry = (
  id: string,
  title: string,
  render: () => ReactNode,
  note: string,
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: 1120,
  render,
  note,
});

/** Записи редактора размещения группы `signature-dates`. */
export const signatureDatesEditorEntries = (): GalleryEntry[] => [
  editorEntry(
    "signature_dates_empty",
    "Рамки дат: пока пустые, пример на сегодня",
    () => (
      <DatesEditor
        slots={{
          supervisor: {
            marks: THREE_MARKS,
            signedAt: null,
            route: { method: "detached" },
          },
        }}
      />
    ),
    "Научрук в маршруте ещё не согласовал: в рамках пример по сегодняшней дате, «Дата появится, когда Петров П. П. подпишет» и лишнее действие подписанту ЭП.",
  ),
  editorEntry(
    "signature_dates_three_marks",
    "«« 13 » ноября 2026 г.» тремя метками",
    () => (
      <DatesEditor
        slots={{
          supervisor: {
            marks: THREE_MARKS,
            signedAt: APPROVED,
            route: { method: "image" },
          },
        }}
      />
    ),
    "День, месяц словом и год двумя цифрами поверх готовых кавычек, черты и «20»; дату дало согласование научрука.",
  ),
  editorEntry(
    "signature_dates_other_page",
    "Дата на другой странице",
    () => (
      <DatesEditor
        slots={{
          academic_supervisor: {
            marks: [SECOND_PAGE],
            signedAt: null,
            route: { method: "image" },
          },
        }}
      />
    ),
    "Метка академрука на стр. 2: «Перейти» листает превью, «Сюда» переносит её на текущую страницу.",
  ),
  editorEntry(
    "signature_dates_manual",
    "Ручная дата вне маршрута",
    () => (
      <DatesEditor
        slots={{
          supervisor: {
            marks: [{ ...SECOND_PAGE, page: 1, y_mm: 152, x_mm: 110 }],
            signedAt: { at: "2026-11-10", source: "manual" },
            route: null,
          },
          academic_supervisor: {
            marks: [
              {
                page: 1,
                x_mm: 110,
                y_mm: 182,
                width_mm: 9,
                height_mm: 4,
                format: "date_numeric",
                align: "center",
              },
            ],
            signedAt: null,
            route: null,
          },
        }}
      />
    ),
    "У научрука указан день, у академрука даты нет («Без даты метки останутся пустыми»), а его рамка мала: «Текст не помещается в рамку».",
  ),
  editorEntry(
    "signature_dates_en",
    "Метки в документе на английском",
    () => (
      <DatesEditor
        lang="en"
        slots={{
          supervisor: {
            marks: [{ ...SECOND_PAGE, page: 1, y_mm: 150, x_mm: 110 }],
            signedAt: APPROVED,
            route: { method: "image" },
          },
        }}
      />
    ),
    "Язык месяца по языку документа: «13 November 2026», примеры в списке форматов тоже английские.",
  ),
  {
    id: "signature_dates_reset",
    title: "Подтверждение сброса подписей",
    note: "Документ под маршрутом, над зафиксированным PDF уже есть ЭП: сохранение меток спрашивает, называет сбрасываемые подписи.",
    frame: "plain",
    render: () => (
      <DialogLauncher label="Открыть окно" defaultOpen={false}>
        {({ isOpen, close }) => (
          <ResetSignaturesDialog
            isOpen={isOpen}
            names={["Петров П. П.", "Сидоров С. С."]}
            pending={false}
            onConfirm={close}
            onCancel={close}
          />
        )}
      </DialogLauncher>
    ),
  },
];
