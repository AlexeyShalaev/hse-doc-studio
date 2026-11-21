import type { QueryClient } from "@tanstack/react-query";
import { packStudioKeys } from "@entities/pack-studio";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import {
  GALLERY_TREE,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import {
  CONTENT_VERSION_DIR,
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

const seedTree = (client: QueryClient) => {
  client.setQueryData(packStudioKeys.tree(GALLERY_WORKSPACE.id), {
    ...GALLERY_TREE,
    files: [
      {
        path: `${CONTENT_VERSION_DIR}/version.yaml`,
        is_dir: false,
        size: 30733,
        read_only: null,
      },
      {
        path: `${CONTENT_VERSION_DIR}/files/common/meta.tex.j2`,
        is_dir: false,
        size: 4120,
        read_only: null,
      },
    ],
  });
};

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
    id: "sp_content_signatures",
    title: "Содержимое: сегмент «Подписи» (до S8c заглушка)",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () =>
      frameFor("doc=technical_specification&seg=signatures", {
        height: "30rem",
      }),
  },
  {
    id: "sp_content_part",
    title: "Содержимое: раздел «Данные проекта»",
    note: "Раздел версии на прежней форме (до S8d).",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () => frameFor("part=fields", { height: "40rem" }),
  },
  {
    id: "sp_content_files",
    title: "Содержимое: «Все файлы»",
    note: "Прежнее дерево для опытных (до S8d).",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContentText(client);
      seedTree(client);
    },
    render: () => frameFor("part=files", { height: "36rem" }),
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
