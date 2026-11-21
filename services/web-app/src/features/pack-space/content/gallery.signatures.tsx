import type { QueryClient } from "@tanstack/react-query";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { GALLERY_REF, SpaceGalleryFrame } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { RELEASED_MODEL, seedContentModel } from "./fixtures";
import { slots } from "./slots";
import {
  SIGNATURES_DOC,
  SIGNATURES_PLAIN,
  SIGNATURES_RELEASED,
  seedSignatures,
} from "./signatures/fixtures";
import { SAMPLE_PDF_URL } from "./signatures/samplePdf";

// Записи галереи «Подписей» (S8c): страница с рамками и карточками, выпущенная версия, документ без
// подписей, раздел «Подписи и места», телефон. Страница-образец лежит в записи.
const RELEASED_REF = { ...GALLERY_REF, version: "2026.1.2" };

const seedDraft = (client: QueryClient) => {
  seedContentModel(client);
  seedSignatures(client, { pdfUrl: SAMPLE_PDF_URL });
};
const seedReleased = (client: QueryClient) => {
  seedContentModel(client, RELEASED_MODEL);
  seedSignatures(client, {
    ref: RELEASED_REF,
    data: SIGNATURES_RELEASED,
    pdfUrl: SAMPLE_PDF_URL,
  });
};
const seedOverview = (client: QueryClient) => {
  seedContentModel(client);
  seedSignatures(client, { data: { ...SIGNATURES_PLAIN } });
};

const frame = (
  search: string,
  options: { phone?: boolean; version?: string; height?: string } = {},
) => (
  <SpaceGalleryFrame
    tab="content"
    search={search}
    {...(options.version ? { version: options.version } : {})}
    height={options.height ?? "46rem"}
  >
    <SpaceScreen slots={slots} phone={options.phone ?? false} />
  </SpaceGalleryFrame>
);

const DOC = `doc=${SIGNATURES_DOC}&seg=signatures`;

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_content_signatures",
    title: "Содержимое, «Подписи»: места подписей по странице документа",
    note: "Рамки подписей на странице и карточки словами: своё место, общее место, подписи без строки в этом PDF. Правка пишется сама.",
    frame: "screen",
    width: 1280,
    seed: seedDraft,
    render: () => frame(DOC),
  },
  {
    id: "sp_content_signatures_released",
    title: "Содержимое, «Подписи»: выпущенная версия",
    note: "Только чтение, рядом «Править копию».",
    frame: "screen",
    width: 1280,
    seed: seedReleased,
    render: () => frame(DOC, { version: RELEASED_REF.version }),
  },
  {
    id: "sp_content_signatures_empty",
    title: "Содержимое, «Подписи»: в документе подписей нет",
    frame: "screen",
    width: 1280,
    seed: seedDraft,
    render: () =>
      frame("doc=source_listing&seg=signatures", { height: "26rem" }),
  },
  {
    id: "sp_content_signatures_overview",
    title: "Содержимое, «Подписи и места»: какие подписи где стоят",
    note: "Сводка версии: подписи, общее место, в каких документах и своё ли у них место; «Расставить» ведёт в документ.",
    frame: "screen",
    width: 1280,
    seed: seedOverview,
    render: () => frame("part=signatures"),
  },
  {
    id: "sp_content_signatures_phone",
    title: "Содержимое, «Подписи»: телефон",
    frame: "plain",
    width: 390,
    seed: seedDraft,
    render: () => frame(DOC, { phone: true, height: "52rem" }),
  },
];
