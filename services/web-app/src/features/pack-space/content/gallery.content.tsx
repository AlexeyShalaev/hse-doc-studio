import type { GalleryEntry } from "@shared/lib/stateGallery";
import { SpaceGalleryFrame } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import {
  RELEASED_MODEL,
  modelWithDocuments,
  seedContentModel,
  seedContentText,
} from "./fixtures";
import { slots } from "./slots";

// Записи галереи области «Содержимое» (S8a): навигация, экран документа с тремя сегментами,
// выпущенная версия, поиск при большом числе документов и телефон. Правая колонка (предпросмотр
// PDF) придёт со срезом S9, поэтому её здесь нет.
const frameFor = (
  search: string,
  options: { phone?: boolean; version?: string; height?: string } = {},
) => (
  <SpaceGalleryFrame
    tab="content"
    search={search}
    {...(options.version ? { version: options.version } : {})}
    {...(options.height ? { height: options.height } : {})}
  >
    <SpaceScreen slots={slots} phone={options.phone ?? false} />
  </SpaceGalleryFrame>
);

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_content_text",
    title: "Содержимое: документ, сегмент «Текст»",
    note: "Слева «что редактируем», в центре название документа, три сегмента и редактор файла (до S8b: прежний редактор).",
    frame: "screen",
    width: 1280,
    seed: seedContentText,
    render: () =>
      frameFor("doc=technical_specification&seg=text", { height: "40rem" }),
  },
  {
    id: "sp_content_terms",
    title: "Содержимое: сегмент «Условия»",
    note: "Форма документа: когда он нужен студенту, название, имя файла.",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () =>
      frameFor("doc=technical_specification&seg=terms", { height: "40rem" }),
  },
  {
    id: "sp_content_released",
    title: "Содержимое: выпущенная версия",
    note: "Замок, плашка «Версия выпущена и не меняется», только чтение.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContentModel(client, RELEASED_MODEL);
    },
    render: () =>
      frameFor("doc=technical_specification&seg=terms", {
        version: "2026.1.2",
        height: "36rem",
      }),
  },
  {
    id: "sp_content_many",
    title: "Содержимое: много документов, поиск в навигации",
    note: "Когда документов больше десяти, над списком появляется поиск.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContentModel(client, modelWithDocuments(16));
    },
    render: () =>
      frameFor("doc=operator_manual&seg=terms", { height: "40rem" }),
  },
  {
    id: "sp_content_phone",
    title: "Содержимое: телефон",
    note: "Слева ничего: «что редактируем» сворачивается полосой над документом.",
    frame: "plain",
    width: 390,
    seed: seedContentModel,
    render: () =>
      frameFor("doc=technical_specification&seg=terms", {
        phone: true,
        height: "40rem",
      }),
  },
];
