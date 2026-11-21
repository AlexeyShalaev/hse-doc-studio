import type { QueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  type PackPlaceEntry,
  type PackPreviewBuild,
  type PackPreviewOptions,
  type PackSignatures,
  type PackSignatureSlot,
} from "@entities/pack-studio";
import { GALLERY_REF, GALLERY_WORKSPACE } from "../../galleryKit";
import { seedDocumentBuild, documentBuildKey } from "./buildSeed";

// Фикстуры «Подписей» для записей галереи и тестов: версия 2026.1.3 из галереи каркаса, документ
// «Техническое задание» с четырьмя подписями (своё место по строке текста, общее место, подпись без
// строки в этом PDF, дата по строке), ещё одна подпись относится только к соглашению.

const WS = GALLERY_WORKSPACE.id;
export const SIGNATURES_DOC = "technical_specification";
export const SIGNATURES_BUILD_ID = "b1c2d3e4-0000-4000-8000-000000000001";
export const SIGNATURES_VERSION_PATH = `${GALLERY_REF.pack}/templates/${GALLERY_REF.template}/versions/${GALLERY_REF.version}/version.yaml`;

const mmEntry = (
  page: number,
  x: number,
  y: number,
  width: number,
): PackPlaceEntry => ({
  source: "mm",
  page,
  x_mm: x,
  y_mm: y,
  width_mm: width,
});

const lineEntry = (
  anchor: string,
  width: number,
  withFallback = true,
): PackPlaceEntry => ({
  source: "anchor",
  anchor,
  align: "right",
  dx_mm: 0,
  dy_mm: -11,
  width_mm: width,
  fallback: withFallback
    ? { page: 1, x_mm: 150, y_mm: 220, width_mm: width }
    : null,
});

type Slot = PackSignatureSlot;
const slot = (fields: Partial<Slot> & Pick<Slot, "id" | "label">): Slot => ({
  applies_to: [SIGNATURES_DOC],
  per_author: false,
  required: false,
  default_place: mmEntry(1, 110, 130, 40),
  default_set: true,
  places: {},
  dates: {},
  document: null,
  ...fields,
});

const AUTHOR = slot({
  id: "author",
  label: { ru: "Автор", en: "Author" },
  per_author: true,
  required: true,
  default_place: mmEntry(1, 160, 208, 30),
  places: { [SIGNATURES_DOC]: lineEntry("author", 30) },
});
const SUPERVISOR = slot({
  id: "supervisor",
  label: { ru: "Руководитель проекта", en: "Project supervisor" },
  required: true,
  applies_to: [SIGNATURES_DOC, "nda"],
});
const CONSULTANT = slot({
  id: "consultant",
  label: { ru: "Консультант", en: "Consultant" },
  default_place: lineEntry("consultant", 28, false),
});
const CUSTOMER = slot({
  id: "customer",
  label: { ru: "Заказчик", en: "Customer" },
  applies_to: ["nda"],
});

/** Подписи версии без сборки: то, что видит раздел «Подписи и места». */
export const SIGNATURES_PLAIN: PackSignatures = {
  workspace_id: WS,
  pack: GALLERY_REF.pack,
  template: GALLERY_REF.template,
  version: GALLERY_REF.version,
  path: SIGNATURES_VERSION_PATH,
  etag: '"sig-1"',
  read_only: null,
  documents: [SIGNATURES_DOC, "nda"],
  build: null,
  slots: [AUTHOR, SUPERVISOR, CONSULTANT, CUSTOMER],
};

/** Они же с рамками документа по сборке PDF. */
export const SIGNATURES_BUILT: PackSignatures = {
  ...SIGNATURES_PLAIN,
  build: {
    id: SIGNATURES_BUILD_ID,
    document: SIGNATURES_DOC,
    anchors_known: true,
    sign_anchors: ["author", "supervisor"],
    date_anchors: ["author.day", "author.month_word"],
  },
  slots: [
    {
      ...AUTHOR,
      document: {
        kind: "place",
        entry: lineEntry("author", 30),
        box: { page: 1, x_mm: 135, y_mm: 201, width_mm: 30 },
        anchor: { id: "author", state: "found" },
        dates: [],
      },
    },
    {
      ...SUPERVISOR,
      document: {
        kind: "default",
        entry: mmEntry(1, 110, 130, 40),
        box: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 },
        anchor: null,
        dates: [],
      },
    },
    {
      ...CONSULTANT,
      document: {
        kind: "default",
        entry: CONSULTANT.default_place,
        box: null,
        anchor: { id: "consultant", state: "missing" },
        dates: [],
      },
    },
    CUSTOMER,
  ],
};

export const SIGNATURES_RELEASED: PackSignatures = {
  ...SIGNATURES_BUILT,
  read_only: "version_released",
};

export const SIGNATURES_PREVIEW_OPTIONS: PackPreviewOptions = {
  workspace_id: WS,
  pack: GALLERY_REF.pack,
  template: GALLERY_REF.template,
  version: GALLERY_REF.version,
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  version_id: GALLERY_REF.version,
  documents: [
    {
      id: SIGNATURES_DOC,
      name: { ru: "Техническое задание", en: "Statement of Work" },
      kinds: [],
      staffing: [],
    },
    {
      id: "nda",
      name: { ru: "Соглашение о неразглашении", en: "NDA" },
      kinds: [],
      staffing: [],
    },
  ],
  switches: [],
  examples: [
    { id: "typical", source: "auto", label: null, error: null, defaults: {} },
  ],
  default_example: "typical",
  combination: {},
};

export const signaturesBuild = (
  status: PackPreviewBuild["status"] = "succeeded",
): PackPreviewBuild => ({
  id: SIGNATURES_BUILD_ID,
  workspace_id: WS,
  pack: GALLERY_REF.pack,
  template: GALLERY_REF.template,
  version: GALLERY_REF.version,
  document: SIGNATURES_DOC,
  example: "typical",
  combination: { lang: "ru" },
  key: "k",
  status,
  cached: false,
  created_at: "2026-11-14T09:30:00Z",
  started_at: "2026-11-14T09:30:01Z",
  finished_at: status === "succeeded" ? "2026-11-14T09:30:09Z" : null,
  pages: 3,
  error: null,
  source_file: null,
  has_anchors: true,
});

/**
 * Всё, что экран берёт у сервера, уже в кэше: условия сборки, готовая сборка, подписи без сборки и
 * по сборке. `readOnly` кладёт выпущенную версию. `pdfUrl` вместо адреса сервера (страница в записи).
 */
export const seedSignatures = (
  client: QueryClient,
  options: {
    ref?: { pack: string; template: string; version: string };
    data?: PackSignatures;
    pdfUrl?: string;
  } = {},
): void => {
  const ref = options.ref ?? GALLERY_REF;
  const data = options.data ?? SIGNATURES_BUILT;
  const plain = { ...data, build: null };
  client.setQueryData(packStudioKeys.previewOptions(WS, ref), {
    ...SIGNATURES_PREVIEW_OPTIONS,
    version: ref.version,
    version_id: ref.version,
  });
  client.setQueryData(
    packStudioKeys.previewBuild(WS, SIGNATURES_BUILD_ID),
    signaturesBuild(),
  );
  client.setQueryData(packStudioKeys.signatures(WS, ref, null), {
    ...plain,
    slots: plain.slots.map((item) => ({ ...item, document: null })),
  });
  client.setQueryData(
    packStudioKeys.signatures(WS, ref, SIGNATURES_BUILD_ID),
    data,
  );
  seedDocumentBuild(WS, ref, SIGNATURES_DOC, {
    buildId: SIGNATURES_BUILD_ID,
    key: documentBuildKey(
      { ...SIGNATURES_PREVIEW_OPTIONS, version: ref.version },
      SIGNATURES_DOC,
      {},
    ),
    ...(options.pdfUrl ? { pdfUrl: options.pdfUrl } : {}),
  });
};
